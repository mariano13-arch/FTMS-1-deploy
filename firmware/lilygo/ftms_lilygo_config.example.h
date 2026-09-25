#ifndef FTMS_LILYGO_CONFIG_H
#define FTMS_LILYGO_CONFIG_H

#include <stdint.h>

// Copy this file to ftms_lilygo_config.h and replace placeholders locally.
// Never commit the local configuration header or real device credentials.
static const char DEVICE_ID[] = "LILYGO-002";
static const char APN[] = "<cellular-apn>";
static const char FTMS_TELEMETRY_URL[] =
  "https://<ftms-host>/api/v1/telemetry/";
static const char VGATE_BT_PIN[] = "<pairing-pin>";
static const char VGATE_BT_NAME[] = "<adapter-name>";
static uint8_t VGATE_BT_ADDRESS[6] = {
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00
};

#endif // FTMS_LILYGO_CONFIG_H
