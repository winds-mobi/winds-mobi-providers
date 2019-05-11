<?php
ini_set('display_errors', 'stderr');

include_once('./m2a.class.php');

$data = new m2a(gpm2hex(fgets(STDIN)));

$json = new stdClass();
$json->infos = $data->getInfos();
$json->timezone = $data->getTimezone();
$json->last_measures = $data->getLastMesures();

// $json->events = $data->getEvents();
// $json->historic = $data->getHistoric();
// $json->active_channels = $data->getActiveChanels();
// $json->measures_blocs = $data->getMeasuresByBlocs();
// $json->measures_sensors = $data->getMeasuresBySensors();

echo json_encode($json, JSON_PARTIAL_OUTPUT_ON_ERROR | JSON_INVALID_UTF8_IGNORE);
?>
