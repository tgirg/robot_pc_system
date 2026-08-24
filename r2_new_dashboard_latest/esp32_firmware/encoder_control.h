#pragma once

#include <Arduino.h>
#include "vehicle_config.h"

class EncoderArray {
public:
  void begin();
  void updateVelocity(float dtSeconds);
  void resetLogical(uint8_t logical, const VehicleConfig& config);
  int32_t logicalCount(uint8_t logical, const VehicleConfig& config) const;
  float logicalRpm(uint8_t logical, const VehicleConfig& config) const;
  uint32_t invalidTransitions(uint8_t logical, const VehicleConfig& config) const;
  bool pcntReady() const;

private:
  static void handleInterrupt0();
  static void handleInterrupt1();
  static void handleInterrupt2();
  static void handleInterrupt3();
  static void handleEdge(uint8_t physical);
};
