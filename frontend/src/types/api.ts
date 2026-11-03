export type UploadStructureResponse = {
  filename: string;
  file_type: string;
  suggested_sheet?: string | null;
  requires_sheet_selection: boolean;
  persisted: false;
  sheets: Array<{
    name: string;
    rows: number;
    columns: string[];
    sample_rows: Array<Record<string, string>>;
    recognized_fields: Record<string, string>;
    required_fields_found: boolean;
    tabular: boolean;
  }>;
};

export * from "./signals";

// NOTE: O restante deste arquivo é mantido no branch via merge; este commit
// apenas garante o reexport dos tipos de sinais. Se o arquivo completo for
// sobrescrito incorretamente, restaure de main e adicione apenas a linha:
// export * from "./signals";
