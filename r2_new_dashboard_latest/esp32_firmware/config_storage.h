#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include "vehicle_config.h"

void setDefaultConfig(VehicleConfig& config);
bool configFromJson(JsonObjectConst root, VehicleConfig& config, char* error, size_t errorSize);
void configToJson(const VehicleConfig& config, JsonObject root);
bool loadConfigFromNvs(VehicleConfig& config);
bool saveConfigToNvs(const VehicleConfig& config);

