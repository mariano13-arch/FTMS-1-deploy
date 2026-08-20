export type DriverIdentity = {
  userId: number;
  username: string;
  driverId: number;
  driverCode: string;
  displayName: string;
  email: string;
  employmentStatus: string;
  employmentStatusLabel: string;
  licenseNumber: string;
  licenseExpiryDate: string | null;
  medicalCertificateExpiryDate: string | null;
  eligibilityStatus: 'ELIGIBLE' | 'RESTRICTED' | 'NOT_ELIGIBLE';
  eligibilityReasons: string[];
};
