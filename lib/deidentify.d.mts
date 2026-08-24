export type RedactionOptions = {
  maskStaffNames?: boolean;
  maskRecordNumbers?: boolean;
};

export type RedactionStats = Record<string, number>;

export type AuditWarning = {
  code: string;
  label: string;
  count: number;
};

export const DEFAULT_OPTIONS: Readonly<Required<RedactionOptions>>;
export const TAGS: Readonly<Record<string, string>>;

export function depersonalizeText(
  input: string,
  options?: RedactionOptions,
  now?: Date,
): { text: string; stats: RedactionStats; warnings: AuditWarning[] };

export function depersonalizePages(
  pages: string[],
  options?: RedactionOptions,
  now?: Date,
): {
  text: string;
  pages: string[];
  stats: RedactionStats;
  warnings: AuditWarning[];
};
