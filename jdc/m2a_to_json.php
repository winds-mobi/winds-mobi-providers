<?php
ini_set('display_errors', 'stderr');

include_once('./m2a.class.php');

$data = new m2a(gpm2hex(base64_decode(fgets(STDIN), $strict=true)));

$json = new stdClass();
$json->infos = $data->getInfos();
$json->timezone = $data->getTimezone();
$json->blocs = $data->getMeasuresByBlocs();

echo json_encode($json, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
?>
