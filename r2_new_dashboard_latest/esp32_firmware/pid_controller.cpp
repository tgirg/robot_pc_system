#include "pid_controller.h"
#include <math.h>

void PidController::reset() {
  _integral = 0.0f;
  _previousError = 0.0f;
}

int16_t PidController::update(float targetRpm, float measuredRpm, const MotorConfig& config, float dtSeconds) {
  if (dtSeconds <= 0.0f || fabsf(targetRpm) < 0.01f) {
    reset();
    return 0;
  }

  float error = targetRpm - measuredRpm;
  _integral += error * dtSeconds;
  _integral = constrain(_integral, -config.integralLimit, config.integralLimit);
  float derivative = (error - _previousError) / dtSeconds;
  _previousError = error;

  float feedForward = 0.0f;
  if (targetRpm > 0.0f) {
    feedForward = config.feedForwardStaticPwmPositive + config.feedForwardPwmPerRpmPositive * fabsf(targetRpm);
  } else {
    feedForward = -(config.feedForwardStaticPwmNegative + config.feedForwardPwmPerRpmNegative * fabsf(targetRpm));
  }

  float output = feedForward + config.kp * error + config.ki * _integral + config.kd * derivative;
  output = constrain(output, (float)config.outputMin, (float)config.outputMax);
  return (int16_t)lroundf(output);
}
