#ifndef DRIVER_BEHAVIOR_PREPROCESSING_H
#define DRIVER_BEHAVIOR_PREPROCESSING_H

const int DRIVER_BEHAVIOR_FEATURE_COUNT = 8;
const int DRIVER_BEHAVIOR_CLASS_COUNT = 4;

const char* driver_behavior_feature_names[] = {
  "AccX",
  "AccY",
  "AccZ",
  "GyroX",
  "GyroY",
  "GyroZ",
  "acc_magnitude",
  "gyro_magnitude",
};

const float driver_behavior_scaler_mean[] = {
  0.25470637f,
  -0.10195551f,
  -0.98463168f,
  -0.79359915f,
  4.18113847f,
  0.72181011f,
  1.05554915f,
  9.57526692f,
};

const float driver_behavior_scaler_scale[] = {
  0.18533922f,
  0.19346908f,
  0.09867190f,
  3.36928185f,
  3.17984302f,
  12.19620308f,
  0.11001290f,
  9.85686681f,
};

const char* driver_behavior_class_names[] = {
  "sudden_acceleration",
  "sudden_braking",
  "sudden_left_turn",
  "sudden_right_turn",
};

#endif // DRIVER_BEHAVIOR_PREPROCESSING_H