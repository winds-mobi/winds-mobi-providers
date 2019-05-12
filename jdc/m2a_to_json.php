<?php
ini_set('display_errors', 'stderr');

include_once('./m2a.class.php');

$data = new m2a(gpm2hex(fgets(STDIN)));

$json = new stdClass();
$json->infos = $data->getInfos();
$json->timezone = $data->getTimezone();
$json->historic = $data->getHistoric();
$json->sensors = $data->getMeasuresBySensors();

echo json_encode($json, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
?>
