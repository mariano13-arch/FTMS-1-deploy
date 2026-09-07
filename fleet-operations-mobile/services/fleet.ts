import { api } from '@/services/api';
import type { TelemetryDevice, Vehicle, VehicleInspectionSummary } from '@/types';

type DeviceSummaryPayload = {
  device_id: string;
  registration_status: string;
};

type VehiclePayload = {
  id: number;
  device_id: string;
  display_name: string;
  plate_number: string;
  vehicle_type: string;
  manufacturer: string;
  model: string;
  is_active: boolean;
  current_telemetry_device: DeviceSummaryPayload | null;
  latest_inspection: null | {
    id: number;
    inspection_date: string;
    inspection_type: string;
    result: string;
  };
};

function mapInspectionSummary(payload: NonNullable<VehiclePayload['latest_inspection']>): VehicleInspectionSummary {
  return {
    id: payload.id,
    inspectionDate: payload.inspection_date,
    inspectionType: payload.inspection_type,
    result: payload.result,
  };
}

type DevicePayload = DeviceSummaryPayload & {
  is_paired: boolean;
  current_vehicle: null | {
    vehicle_id: number;
    plate_number: string;
    display_name: string;
    compatibility_device_id: string;
  };
};

function mapVehicle(payload: VehiclePayload): Vehicle {
  return {
    id: payload.id,
    compatibilityDeviceId: payload.device_id,
    displayName: payload.display_name,
    plateNumber: payload.plate_number,
    vehicleType: payload.vehicle_type,
    manufacturer: payload.manufacturer,
    model: payload.model,
    isActive: payload.is_active,
    currentTelemetryDevice: payload.current_telemetry_device
      ? {
          deviceId: payload.current_telemetry_device.device_id,
          registrationStatus: payload.current_telemetry_device.registration_status,
        }
      : null,
    latestInspection: payload.latest_inspection ? mapInspectionSummary(payload.latest_inspection) : null,
  };
}

function mapDevice(payload: DevicePayload): TelemetryDevice {
  return {
    deviceId: payload.device_id,
    registrationStatus: payload.registration_status,
    isPaired: payload.is_paired,
    currentVehicle: payload.current_vehicle
      ? {
          vehicleId: payload.current_vehicle.vehicle_id,
          plateNumber: payload.current_vehicle.plate_number,
          displayName: payload.current_vehicle.display_name,
          compatibilityDeviceId: payload.current_vehicle.compatibility_device_id,
        }
      : null,
  };
}

export async function getVehicles(signal?: AbortSignal): Promise<Vehicle[]> {
  const response = await api<{ results: VehiclePayload[] }>('/api/v1/vehicles/?page_size=100', {
    signal,
  });
  return response.results.map(mapVehicle);
}

export async function getVehicle(
  compatibilityDeviceId: string,
  signal?: AbortSignal,
): Promise<Vehicle> {
  const response = await api<VehiclePayload>(
    `/api/v1/vehicles/${encodeURIComponent(compatibilityDeviceId)}/`,
    { signal },
  );
  return mapVehicle(response);
}

export async function getTelemetryDevice(
  deviceId: string,
  signal?: AbortSignal,
): Promise<TelemetryDevice> {
  const response = await api<DevicePayload>(
    `/api/v1/telemetry-devices/${encodeURIComponent(deviceId)}/`,
    { signal },
  );
  return mapDevice(response);
}

export async function pairTelemetryDevice(
  deviceId: string,
  vehicleId: number,
  replaceCurrent: boolean,
): Promise<TelemetryDevice> {
  const response = await api<DevicePayload>(
    `/api/v1/telemetry-devices/${encodeURIComponent(deviceId)}/pair/`,
    {
      method: 'POST',
      body: JSON.stringify({ vehicle_id: vehicleId, replace_current: replaceCurrent }),
    },
  );
  return mapDevice(response);
}

export async function unpairTelemetryDevice(deviceId: string): Promise<TelemetryDevice> {
  const response = await api<DevicePayload>(
    `/api/v1/telemetry-devices/${encodeURIComponent(deviceId)}/unpair/`,
    { method: 'POST', body: JSON.stringify({}) },
  );
  return mapDevice(response);
}
