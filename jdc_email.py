import email
import imaplib
import json
import subprocess
from email.policy import EmailPolicy

from commons.provider import Provider
from settings import JDC_IMAP_SERVER, JDC_IMAP_USERNAME, JDC_IMAP_PASSWORD


class Jdc(Provider):
    provider_code = 'madd'
    provider_name = 'madd.ch'
    provider_url = 'https://www.jdc.ch'

    def __init__(self):
        super().__init__()

        self.imap_server = JDC_IMAP_SERVER
        self.imap_username = JDC_IMAP_USERNAME
        self.imap_password = JDC_IMAP_PASSWORD

    def m2a_to_json(self, data: bytes):
        proc = subprocess.Popen(['php', 'm2a_to_json.php'], cwd='jdc', stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        proc.stdin.write(data)
        proc.stdin.close()
        result = proc.stdout.read()
        proc.wait()
        return json.loads(result)

    def process_data(self):
        try:
            self.log.info('Processing JDC data...')

            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.imap_username, self.imap_password)
            try:
                typ, data = mail.select()
                nb_msg = int(data[0])
                self.log.info(f"There are {nb_msg} messages in the inbox")

                for i in range(1, nb_msg + 1):
                    try:
                        typ, data = mail.fetch(str(i), '(RFC822)')
                        message = email.message_from_bytes(data[0][1], policy=email.policy.default)
                        jdc_payload = message.get_payload(1)
                        jdc_filename = jdc_payload.get_filename()
                        jdc_content = jdc_payload.get_payload(decode=True)
                        try:
                            jdc_station = self.m2a_to_json(jdc_content)
                            jdc_id = jdc_station['infos']['serial']
                            jdc_name = jdc_station['infos']['site']
                            measures = jdc_station['last_measures']
                            self.log.info(f"Station '{jdc_id}' ({jdc_name}) found {len(measures)} sensor values")
                            typ, data = mail.store(str(i), '+FLAGS', r'\Deleted')
                            if not typ == 'OK':
                                self.log.warning(f"Unable to delete email '{message['subject']}'")
                        except Exception as e:
                            self.log.error(f"Unable to parse attachment '{jdc_filename}': {e}")
                    except Exception:
                        self.log.exception(f'Unable to load email #{i}')
            finally:
                mail.expunge()
                mail.logout()

        except Exception as e:
            self.log.exception(f'Error while processing JDC: {e}')

        self.log.info('Done !')


Jdc().process_data()
