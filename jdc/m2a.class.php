<?php
/**
 * Traîtement des données M2A (MultiMADD2 et stations N.E.W.S.)
 *
 * <p>Traîtement de données M2A</p>
 *
 * @name m2a
 * @author Gérald Monin <g.monin@madd.ch>
 * @copyright MADD Technologies Sàrl
 * @version 1.2.1
 * @date 21.02.2012
 * @package m2a.class
 *
 * @modifications:
 * 1.2: Add N.E.W.S version 1.6
 * 1.2.1: Add specific timezone for some stations (Caloocan). May 2015
 */

// Conversion d'un fichier GPM en fichier hexa
function gpm2hex($content) {
  $inter = '';
  foreach (str_split($content) as $byte) {
    if (($byte > '?') && ($byte < 'P')) {
      $inter .= $byte;
    }
  }
  $output = '';
  foreach (str_split($inter,2) as $binome) {
    $msb = ord(substr($binome,0,1));
    $msb = $msb % 16;
    $msb = dechex($msb);
    $lsb = ord(substr($binome,1,1));
    $lsb = $lsb % 16;
    $lsb = dechex($lsb);

    $output .= chr(hexdec($msb.$lsb));
  }
  return $output;
}

// Conversion d'une chaîne ASCII en BCD
function txt2bcd($text) {
  $bcd = '';
  foreach (str_split($text) as $byte) {
    $bcd .= dechex(ord($byte)/16) . dechex(ord($byte)%16);
  }
  return $bcd;
}

// Formatage de la taille d'un fichier
function format_bytes($size) {
    $units = array(' B', ' kB', ' MB', ' GB', ' TB');
    for ($i = 0; $size >= 1024 && $i < 4; $i++) $size /= 1024;
    return round($size, 2).$units[$i];
}

// Conversion d'un nombre de secondes (avec ou sans timezone) en temps, selon la version du firmware
function hex2time($seconds, $version, $timezone=null) {
  if ($version >= 1.2) {
    $tmz = str_split(pack("V",$seconds));
    $tmz = (ord($tmz[3]) & 192) >> 6;
    $seconds &= 1073741823;   // Supprimer l'info du timezone
    // Traîte un timezone spécifique
    if ($timezone)
      $tmz = $timezone;
    $seconds -= $tmz * 3600;
    $time = gmmktime(0, 0, $seconds, 1, 1, 2000);
  } else {
    $time = mktime(0, 0, $seconds, 1, 1, 2000, 0);
    $gmt_offset = date('Z', $time);
    $time = $time - $gmt_offset;
  }
  return $time;
}

function mydate($format, $t){
  $temps = new DateTime(gmdate($format,$t), new DateTimeZone('GMT'));
  date_timezone_set($temps, timezone_open('Etc/GMT-1'));
  return $temps->format($format);
}

// Calcul du nombre de canaux de mesures en fonction de la programmation
function usrprog2chanels($usrProg, $prgOpts) {
  $chanels = 0;

  if (($usrProg & 1)  > 0) $chanels += 1;
  if (($usrProg & 2)  > 0) $chanels += 2;
  if (($usrProg & 4)  > 0) $chanels += 4;
  if (($usrProg & 8)  > 0) $chanels += 8;
  if (($usrProg & 16) > 0) $chanels += 1;
  if (($usrProg & 32) > 0) $chanels += 7;
  if (($usrProg & 64) > 0) {
    switch ($prgOpts & 12) {
      case 12:
        $chanels += 6;
        break;
      case 8:
        $chanels += 5;
        break;
      case 4:
        $chanels += 3;
        break;
      default:
        $chanels += 5;
        break;
    }
  }

  return $chanels;
}

// Calcul du numéro du canal en fonction du numéro de la mesure et de la programmation
function noMes2noCanal($noMes, $usrProg, $prgOpts) {
  $chanels = 0;
  if ($usrProg & 1) {
    if ($noMes < 1) return 0; else $noMes -= 1;
    $chanels += 1;
  }
  if ($usrProg & 2) {
    if ($noMes < 2) return $chanels+$noMes; else $noMes -= 2;
    $chanels += 2;
  }
  if ($usrProg & 4) {
    if ($noMes < 4) return $chanels+$noMes; else $noMes -= 4;
    $chanels += 4;
  }
  if ($usrProg & 8)
    if ($noMes < 8) return $chanels+$noMes; else $noMes -= 8;
  $chanels = 8;

  switch ($prgOpts & 12) {
    case 12:
      if ($usrProg & 64)
        if ($noMes < 6) return $chanels+$noMes; else $noMes -= 6;
      $chanels += 12;
      break;
    case 8:
      if ($usrProg & 64)
        if ($noMes < 5) return $chanels+$noMes; else $noMes -= 5;
      $chanels += 12;
      break;
    case 4:
      if ($usrProg & 64)
        if ($noMes < 3) return $chanels+$noMes; else $noMes -= 3;
      $chanels += 12;
      break;
    default:
      if ($usrProg & 32)
        if ($noMes < 7) return $chanels+$noMes; else $noMes -= 7;
      $chanels += 7;
      if ($usrProg & 64)
        if ($noMes < 5) return $chanels+$noMes; else $noMes -= 5;
      $chanels += 5;
      break;
  }

  if ($usrProg & 16)
    if ($noMes < 1) return $chanels+$noMes; else $noMes -= 1;
  $chanels += 1;
  return 20;
}

// Classe M2A
class m2a {
  // Propriétés
  private $type, $serial, $version, $mode, $nbCanaux, $site;
  private $timezone;
  private $memPtr, $histo, $tension, $rssi, $lastMeasures;
  private $names;
  private $chConf;
  private $pluMem;
  private $mesMem, $mesBlocs;

  // Constructeurs
  public function __construct($data) {
    $this->type = substr($data,0,2);
    $this->serial = txt2bcd(substr($data,2,2));
    $this->version = ord(substr($data,4,1))/10;
    $this->mode = dechex(ord(substr($data,5,1)));
    $this->nbCanaux = ord(substr($data,7,1));
    $this->site = trim(utf8_encode(substr($data,8,32)));

    // Définir un timezone spécifique pour certaines stations
    switch ($this->serial) {
      case 1021: // Philippines
        $this->timezone = 8;
        break;
      default:
        $this->timezone = NULL;
        break;
    }

    $this->memPtr = unpack("V*",substr($data,40,24));
    $this->histo = unpack("V*",substr($data,64,28));
    $tension = unpack("v",substr($data,92,2));
    $this->tension = round($tension[1]/1000,2);
    $rssi = substr($data,94,2);
    $this->rssi = (!is_numeric($rssi) or $rssi == 99) ? 'NC' : $rssi * 2 - 113;
    $this->lastMeasures = unpack("v*",substr($data,96,40));

    $this->chConf = array();
    foreach (str_split(substr($data,136,21*16),16) as $conf) {
      $this->chConf[] = new m2a_chconf($conf);
    }

    // Noms des canaux
    $this->names = array();
    for ($i=0; $i<21; $i++) {
      if ($this->type == 'M2') {
        $this->names[] = trim(substr($data,472+$i*32,32));
      } else {
        $this->names[] = '';
      }
    }

    // Calcul des tailles des mémoires
    $startOfPlu = (($this->type == 'M2') || ($this->version > 1.6))?1144:472;
    $lenData = strlen($data);
    $startOfMes = strpos($data, chr(255).chr(255).chr(255).chr(255), $startOfPlu < $lenData ? $startOfPlu : 0);
    $sizeOfPlu = $startOfMes - $startOfPlu;
    $sizeOfMes = $lenData - $startOfMes;
    $this->pluMem = substr($data,$startOfPlu,$sizeOfPlu);
    $this->mesMem = substr($data,$startOfMes,$sizeOfMes);

    // Traîter les blocs de  mesures
    $this->mesBlocs = array();
    $blocs = explode(chr(255).chr(255).chr(255).chr(255), $this->mesMem);
    array_splice($blocs,0,1);
    foreach ($blocs as $i => $bloc) {
      $this->mesBlocs[] = new m2a_mesBloc($this, $bloc);
    }
  }

  // Retourne la version du firmware
  public function getVersion() {
    return $this->version;
  }
  // Retourne le timezone de la station
  public function getTimezone() {
    return $this->timezone;
  }

  // Retourne la taille et l'occupation des mémoires
  public function getMemSizes() {
    return array('pluMem' => strlen($this->pluMem),
                 'pluUse' => round(($this->memPtr[3]-$this->memPtr[1])/(hexdec('1D000'))*100,2),
                 'mesMem' => strlen($this->mesMem),
                 'mesUse' => round(($this->memPtr[6]-$this->memPtr[4])/(hexdec('60000'))*100,2));
  }

  // Retourne les informations générales de la station sous forme de tableau
  public function getInfos() {
    $types = array('M2' => 'MultiMADD2', 'SF' => 'N.E.W.S.');
    return array('type' => $this->type,
                 'appareil' => $types[$this->type],
                 'serial' => $this->serial,
                 'version' => $this->version,
                 'site' => $this->site,
                 'pluSize' => $this->memPtr[3]-$this->memPtr[1],
                 'mesSize' => $this->memPtr[6]-$this->memPtr[4]);
  }

  // Retourne les événements sous forme de tableau
  public function getEvents() {
    $events = array();
    foreach (unpack("V*",$this->pluMem) as $event) {
      $events[] = hex2time($event, $this->version, $this->timezone);
    }
    return $events;
  }

  // Retourne les infos et la valeur corrigée d'un canal
  public function getChInfos($canal, $mesure) {
    $mesure = $this->chConf[$canal]->scaleMeasure($mesure);
    $status = $this->chConf[$canal]->getStatus();
    return array('canal' => $canal,
                 'id' => $this->chConf[$canal]->getID(),
                 'type' => $this->chConf[$canal]->getType(),
                 'res' => $this->chConf[$canal]->getRes(),
                 'offset' => $this->chConf[$canal]->getOffset(),
                 'name' => $this->names[$canal],
                 'valeur' => $mesure,
                 'unit' => $this->chConf[$canal]->getUnit(),
                 'status' => $status['En']);
  }

  // Retourne le statut d'un canal
  public function getChStatus($canal) {
    return $this->chConf[$canal]->getStatus();
  }
  public function getChStatusFlag($canal, $index) {
    $status = $this->chConf[$canal]->getStatus();
    return $status[$index];
  }

  // Retourne le canal AD d'un canal
  public function getChAdChannel($canal) {
    return $this->chConf[$canal]->getAdChannel();
  }

  // Retourne la baleur d'un événement (basculement d'auget)
  public function getValEvent() {
    $val = substr($data,468,2);
    return $val/10;
  }

  // Retourne l'index d'un canal selon l'ID. Retourne -1 si il n'existe pas.
  public function getIndexFromID($ID) {
    $found = -1;
    foreach ($this->chConf as $i => $conf) {
      if ($conf->getID() == $ID) {
        $found = $i;
        break;
      }
    }
    return $found;
  }

  // Retourne les derniéres mesures
  public function getLastMesures() {
    $i = 1;
    $data = array();
    $actives = $this->getActiveChanels();
    foreach ($actives as $actif) {
      $mesure = $this->chConf[$actif]->scaleMeasure($this->lastMeasures[$i]);
      $data[] = array('canal' => $actif,
                      'type' => $this->chConf[$actif]->getType(),
                      'valeur' => $mesure,
                      'unit' => $this->chConf[$actif]->getUnit());
      $i++;
    }
    return $data;
  }

  // Retourne l'historique de la station
  public function getHistoric() {
    return array('lastMes' => date('d.m.Y H:i:s O',hex2time($this->histo[2],$this->version)),
                 'lastMail' => date('d.m.Y H:i:s O',hex2time($this->histo[4],$this->version)),
                 'lastUSB' => date('d.m.Y H:i:s O',hex2time($this->histo[7],$this->version)),
                 'tension' => $this->tension,
                 'rssi' => $this->rssi,
                 'mesures' => $this->getLastMesures());
  }

  // Retourne un tableau des canaux actifs
  public function getActiveChanels() {
    $actives = array();
    for ($i=0; $i<21; $i++) {
      if ($this->getChStatusFlag($i,'En')) {
        $actives[] = $i;
      }
    }
    return $actives;
  }

  // Retourne toutes les mesures de la mémoire par blocs
  public function getMeasuresByBlocs() {
    $data = array();
    foreach($this->mesBlocs as $bloc) {
      $data[] = $bloc->getBloc();
    }
    return $data;
  }

  // Retourne toutes les mesures de la mémoire par capteurs
  public function getMeasuresBySensors() {
    $sensors = array();
    foreach($this->mesBlocs as $bloc) {
      // Récupérer toutes les informations et mesures du bloc
      $data = $bloc->getBloc();
      // Traiter toutes les séries de mesures par capteur
      $i=0;
      foreach($data['mesures'] as $serie) {
        foreach($serie['mesures'] as $capteur) {
          if ($i == 0) {
            $sensors[$capteur['canal']]['id'] = $capteur['id'];
            $sensors[$capteur['canal']]['type'] = $capteur['type'];
            $sensors[$capteur['canal']]['unit'] = $capteur['unit'];
            $sensors[$capteur['canal']]['status'] = $capteur['status'];
          }
          $sensors[$capteur['canal']]['mesures'][] = array('datetime' => $serie['datetime'], 'valeur' => $capteur['valeur']);
        }
        $i++;
      }

      // Ajouter la tension des batteries et le niveau RSSI
      $sensors[21]['id'] = 'Alim';
      $sensors[21]['type'] = "Tension d'alimentation";
      $sensors[21]['unit'] = 'V';
      $sensors[21]['status'] = 1;
      $sensors[21]['mesures'][] = array('datetime' => $data['datetime'], 'valeur' => $data['tension']);
      $sensors[22]['id'] = 'Rssi';
      $sensors[22]['type'] = "Niveau RSSI";
      $sensors[22]['unit'] = 'dBm';
      $sensors[22]['status'] = 1;
      $sensors[22]['mesures'][] = array('datetime' => $data['datetime'], 'valeur' => $data['rssi']);
    }
    return $sensors;
  }

  // Retourne un tableau des capteurs actifs et de leur configuration
  public function getActiveSensors() {
    $data = array();
    foreach($this->mesBlocs as $bloc) {
      $data[] = $bloc->getActiveSensors();
    }
    return $data;
  }

  // Génére un fichier d'exportation des données sous forme tabulaire
  public function export() {
    // Exporter l'entête du fichier
    $infos = $this->getInfos();
    $exFileName = $infos['serial']."_".date('YmdHis').".txt";
    $exFileContent  = $infos['appareil']." n° ".$infos['serial']."\n";
    $exFileContent .= "Site:\t".$infos['site']."\n";
    $exFileContent .= "\n";
    $exFileContent .= "Version:\t".number_format($infos['version'],1)."\n";
    $memsizes = $this->getMemSizes();
    $exFileContent .= "Mémoire:\t".number_format($memsizes['mesUse'],1)." %\n";
    $historic = $this->getHistoric();
    $exFileContent .= "Batteries:\t".number_format($historic['tension'],1)." V\n";
    $exFileContent .= "\n";
    $exFileContent .= "\n";

    // Traiter les événements
    // Est-ce que les événements sont activés ?
    if ($this->getChStatusFlag(20, 'En')) {
      // Oui, préparer l'entéte des événements
      $exFileContent .= "Evénements:\n";
      $sensor = $this->getChInfos(20, 0);
      $exFileContent .= "Date et heure\t".$sensor['type']."[".$sensor['unit']."]\n";
      // Inscrire les événements
      foreach($this->getEvents() as $event) {
        $exFileContent .= mydate(TIME_FORMAT,$event)."\t".$this->getValEvent()."\n";
      }
      $exFileContent .= "\n\n";
    }

    // Traiter les mesures
    // Préparer l'entéte des mesures
    $exFileContent .= "Mesures:\n";
    $exFileContent .= "Date et heure";
    $tmpData = array();
    foreach($this->getMeasuresBySensors() as $channel => $sensor) {
      $exFileContent .= "\t".$sensor['type']." [".$sensor['unit']."]";
//            $exFileContent .= "\t".$sensor['type']." (".$sensor['name'].") [".$sensor['unit']."]";
      // Enregistrer les mesures dans un tableau
      foreach ($sensor['mesures'] as $mesure) {
        $tmpData[mydate(TIME_FORMAT,$mesure['datetime'])][$channel] = $mesure['valeur'];
      }
    }
    foreach($tmpData as $time => $tabMes) {
      $exFileContent .= "\n".$time;
      foreach ($tabMes as $mesure) {
        $exFileContent .= "\t".$mesure;
      }
    }

    return array('type' => $this->type,
                 'serial' => $this->serial,
                 'filename' => $exFileName,
                 'content' => $exFileContent);
  }

  // Valide les mesures selon le type de capteur
  public function getValidatedMeasurements() {
    global $db;
    $data = $this->getMeasuresBySensors();

    // 1. Tester un timeout du capteur WS (humidité = 409.6) -> Supprimer les mesures de cette heure-là
    //                                    (humidité = 409) -> Supprimer toutes les données de cette heure-là
    if (isset($data[19])) {
      foreach ($data[19]['mesures'] as $row) {
        if ($row['valeur'] == 4096) {
          // Humidité = 409.6 -> Effacer les mesures de cette heure-là
          foreach ($data as $canal => $données) {
            if (($canal > 14) && ($canal < 20 )) {
              foreach ($données['mesures'] as $n => $vals) {
                if ($vals['datetime'] == $row['datetime']) {
                  array_splice($data[$canal]['mesures'], $n, 1);
                }
              }
            }
          }
        }
      }
    }

    // 2. Tester chaque capteur selon ses limites
    // Récupérer les capteurs, leurs unités et les infos liées aux unités
    foreach ($data as $canal => $données) {
      $unit = $db->getUnitData($données['unit']);
      if ($unit['test']>0) {
        $newdata = array();
        foreach ($données['mesures'] as $vals) {
          if (($vals['valeur'] >= $unit['validation_min']) && ($vals['valeur'] <= $unit['validation_max'])) {
            $newdata[] = $vals;
          }
        }
        $data[$canal]['mesures'] = $newdata;
      }
    }

    return $data;
  }

  // Destructeur
  public function __destruct() {

  }
}

/*****************************************************************/
/* Classe représentant un bloc de mesures avec son entête et ses mesures  */
/*****************************************************************/
class m2a_mesBloc {
  // Propriétés
  private $station;
  private $tailleBloc, $usrProg, $prgOpts, $etats, $nbCanaux;
  private $tension, $rssi, $datetime, $interval;
  private $series;

  // Constructeur
  public function __construct($station, $bloc) {
    $this->station = $station;
    $this->tailleBloc = ord(substr($bloc,0,1));
    $this->usrProg = ord(substr($bloc,1,1));
    $this->prgOpts = ord(substr($bloc,2,1));
    $horodatage = ($this->prgOpts & 1) > 0;
    $this->etats = ord(substr($bloc,3,1));
    $this->nbCanaux = usrprog2chanels($this->usrProg, $this->prgOpts);
    $tension = unpack("v",substr($bloc,4,2));
    $this->tension = round($tension[1]/1000,2);
    $rssi = substr($bloc,6,2);
    $this->rssi = (!is_numeric($rssi) or $rssi == 99) ? 'NC' : $rssi * 2 - 113;
    $datetime = unpack("V",substr($bloc,8,4));
    $this->datetime = hex2time($datetime[1], $station->getVersion(), $station->getTimezone());
    $interval = unpack("v*",substr($bloc,12,4));
    $this->interval = (!$interval[2]) ? $interval[1] * 300 : $interval[1] * $interval[2];
    $serieLen = ($horodatage) ? 2 * $this->nbCanaux + 4 : 2 * $this->nbCanaux;

    // Traîter toutes les séries de mesures
    $this->series = array();
    foreach (str_split(substr($bloc,$this->tailleBloc-4,strlen($bloc)),$serieLen) as $serie) {
      if (strlen($serie) < $serieLen)  break;
      $this->series[] = new m2a_mesSerie($serie, $horodatage, $station->getVersion(), $station->getTimezone());
    }
  }

  // Retourne les infos et les mesures du bloc de mesures
  public function getBloc() {
    $series = array();
    foreach ($this->series as $serie) {
      $temp = $serie->getSerie();
      $mesures = array();
      foreach ($temp[1] as $no => $mesure) {
        $noCanal = noMes2noCanal($no-1, $this->usrProg, $this->prgOpts);
        $mesures[] = $this->station->getChInfos($noCanal,$mesure);
      }
      $series[] = array('datetime' => $temp[0], 'mesures' => $mesures);
    }
    return array('nbCanaux' => $this->nbCanaux,
                 'tension' => $this->tension,
                 'rssi' => $this->rssi,
                 'datetime' => $this->datetime,
                 'interval' => $this->interval,
                 'mesures' => $series);
  }

  // Retourne les infos des capteurs actifs
  public function getActiveSensors() {
    $sensors = array();
    $nbCh = usrprog2chanels($this->usrProg, $this->prgOpts);
    for ($i=0; $i < $nbCh; $i++) {
      $sensors[noMes2noCanal($i, $this->usrProg, $this->prgOpts)] = $this->station->getChInfos(noMes2noCanal($i, $this->usrProg, $this->prgOpts),0);
    }
    // Ajouter la tension des batteries et le niveau RSSI
    $sensors[21] = array('id' => 'Alim', 'type' => "Tension d'alimentation", 'unit' => 'V', 'status' => 1);
    $sensors[22] = array('id' => 'Rssi', 'type' => "Niveau RSSI", 'unit' => 'dBm', 'status' => 1);

    return $sensors;
  }
}

/****************************************/
/* Classe représentant une série de mesures  */
/***************************************/
class m2a_mesSerie {
  // Propriétés
  private $datetime, $mesures;

  // Constructeur
  public function __construct($serie, $horodatage, $version, $timezone) {
    if ($horodatage) {
      $seconds = unpack("V",$serie);
      $this->datetime = hex2time($seconds[1], $version, $timezone);
      $this->mesures = unpack("v*",substr($serie,4,strlen($serie)));
    } else {
      $this->datetime = '';
      $this->mesures = unpack("v*",substr($serie,0,strlen($serie)));
    }
  }

  // Retourne un tableau avec la date et l'heure des mesures ainsi que les mesures
  public function getSerie() {
    return array($this->datetime, $this->mesures);
  }
}

/*********************************************/
/* Classe représentant la configuration d'un canal  */
/*********************************************/
class m2a_chconf {
  // Propriétés
  private $chTypes = array(0 => 'Type non défini',
    1 => 'Pluviométrie',
    2 => 'Vent moyen',
    3 => 'Vent max',
    4 => 'Direction du vent',
    5 => 'Température de l\'air',
    6 => 'Température de l\'eau',
    7 => 'Température du sol',
    8 => 'Humidité',
    9 => 'Pression atmosphérique',
    10 => 'Ensoleillement',
    20 => 'Hauteur d\'eau',
    21 => 'Niveau',
    22 => 'Débit',
    25 => 'Distance',
    30 => 'Ecartement',
    31 => 'Déplacement',
    32 => 'Vitesse',
    33 => 'Temps',
    40 => 'Courant',
    41 => 'Tension',
    42 => 'Puissance',
    50 => 'Force',
    99 => 'Autre');
  private $type, $options, $etats, $adCanal;
  private $idCanal, $p10n, $unit, $offset;

  // Constructeurs
  public function __construct($data) {
    $this->type = ord(substr($data,0,1));
    $this->options = ord(substr($data,1,1));
    $this->etats = ord(substr($data,2,1));
    $this->adCanal = ord(substr($data,3,1));
    $this->idCanal = substr($data,4,2);
    $this->p10n = ord(substr($data,6,1));
    $this->unit = trim(utf8_encode(substr($data,7,5)));
    // L'offset est en big endian, contrairement au reste
    $off = unpack("n*",substr($data,12,4));
    if ($off[1] >= 32768)
      $this->offset = ($off[1]*65536+$off[2]) - pow(2, 32);
    else
      $this->offset = $off[1]*65536+$off[2];
  }

  // Retourne le type de canal
  public function getType() {
    return $this->chTypes[$this->type];
  }

  // Retourne le canal AD du canal
  public function getAdChannel() {
    return $this->adCanal;
  }

  // Retourne l'ID du canal
  public function getID() {
    return $this->idCanal;
  }

  // Retourne la résolution d'un canal
  public function getRes() {
    return array('sign' => ($this->p10n & 128) && 1, 'aff' => ($this->p10n & 112) >> 4, 'mes' => $this->p10n & 15);
  }

  // Retourne une mesure à la bonne résolution et en tenant compte de l'offset
  public function scaleMeasure($mes) {
    $res = $this->getRes();

    $val = ($res['sign'] && ($mes>=32768)) ? $mes-65536 : $mes;
    if ($this->idCanal <> 'PL')
      $val += $this->offset;
    return round($val / pow(10, $res['mes']),$res['aff']);
  }

  // Retourne l'unité
  public function getUnit() {
    return $this->unit;
  }

  // Retourne l'offset
  public function getOffset() {
    return $this->offset;
  }

  // Retourne le status du capteur
  public function getStatus() {
    $status = array();
    $status['En'] = (bool)($this->etats & 128);
    $status['AlEn'] = (bool)($this->etats & 64);
    $status['Alert'] = (bool)($this->etats & 32);
    $status['Prealert'] = (bool)($this->etats & 16);
    $status['StartOf'] = (bool)($this->etats & 4);
    $status['InAlert'] = (bool)($this->etats & 2);
    $status['InPalert'] = (bool)($this->etats & 1);
    return $status;
  }

  // Destructeur
  public function __destruct() {

  }
}
?>