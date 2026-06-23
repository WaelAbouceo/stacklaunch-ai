import type { CRMRecord } from "../types";

// Mask an email like ahmed.hassan@example.com -> ah***@example.com
export function maskEmail(email: string): string {
  const [local, domain] = email.split("@");
  if (!domain) return "***";
  const visible = local.slice(0, 2);
  return `${visible}***@${domain}`;
}

// Mask a phone like +201012345678 -> +20******678
export function maskPhone(phone: string): string {
  const digits = phone.replace(/[^\d+]/g, "");
  if (digits.length <= 6) return "+20******";
  const prefix = digits.slice(0, 3);
  const suffix = digits.slice(-3);
  return `${prefix}******${suffix}`;
}

// Mask a name like "Ahmed Hassan" -> "A. Hassan" (or fully when maskNames=true).
export function maskName(name: string, fully = false): string {
  if (!fully) return name;
  const parts = name.split(" ");
  if (parts.length === 1) return `${parts[0][0]}***`;
  return `${parts[0][0]}. ${parts[parts.length - 1][0]}***`;
}

export interface MaskOptions {
  maskNames: boolean;
}

// Returns a masked copy of a CRM record for display. PII (email/phone) is
// always masked; names are masked only when maskNames is enabled.
export function maskCRMRecord(record: CRMRecord, options: MaskOptions): CRMRecord {
  return {
    ...record,
    name: maskName(record.name, options.maskNames),
    email: maskEmail(record.email),
    phone: maskPhone(record.phone),
  };
}

export function maskCRMRecords(records: CRMRecord[], options: MaskOptions): CRMRecord[] {
  return records.map((r) => maskCRMRecord(r, options));
}

// Reference a customer in assistant answers without exposing PII.
export function safeCustomerReference(record: CRMRecord): string {
  return `${record.customerId} (${record.segment}, ${record.city})`;
}
