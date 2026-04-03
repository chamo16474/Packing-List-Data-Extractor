const API = "http://localhost:8080";

export type FieldName = 
  | "lot" 
  | "pieces" 
  | "meters" 
  | "po_number" 
  | "net_weight" 
  | "order_number" 
  | "invoice_number" 
  | "delivered_date" 
  | "quality" 
  | "color";

export type ConfidenceStatus = "auto" | "review" | "flag" | "na";

export interface ExtractedField {
  value: string | number | null;
  confidence: number;
  mapping_source: string;
  source_page?: number;
  source_text?: string;
  status?: ConfidenceStatus; // Derived status
  actioned?: boolean;
}

export interface UploadResponse {
  job_id: string;
  fields: Record<FieldName, ExtractedField>;
  flagged_fields: FieldName[];
  raw_text?: { page: number; text: string }[];
}

export interface Candidate {
  value: string | number;
  confidence: number;
}

/** Upload a PDF */
export async function uploadFile(file: File, supplierName?: string): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (supplierName) form.append("supplier_name", supplierName);
  
  const res = await fetch(`${API}/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown backend error" }));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

/** Get full result */
export async function getResult(jobId: string): Promise<UploadResponse> {
  const res = await fetch(`${API}/result/${jobId}`);
  if (!res.ok) throw new Error("Failed to fetch result");
  return res.json();
}

/** Get reassign candidates for a field */
export async function getCandidates(jobId: string, fieldName: FieldName): Promise<Candidate[]> {
  const res = await fetch(`${API}/mapping/candidates/${jobId}/${fieldName}`);
  if (!res.ok) throw new Error("Failed to fetch candidates");
  const data = await res.json();
  return data.candidates.map((val: any) => ({ value: val, confidence: 100 }));
}

/** Confirm / reassign / mark N/A */
export async function submitAction(
  jobId: string, 
  fieldName: FieldName, 
  value: string | number | null, 
  action: "CONFIRM" | "REASSIGN" | "NA"
): Promise<{ success: boolean }> {
  const backendActionMap = {
    "CONFIRM": "confirm",
    "REASSIGN": "reassign",
    "NA": "not_present"
  };

  const res = await fetch(`${API}/mapping/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, field_name: fieldName, confirmed_value: value, action: backendActionMap[action] })
  });
  if (!res.ok) throw new Error("Action failed");
  return res.json();
}

/** Download Excel */
export async function downloadExcel(jobId: string): Promise<void> {
  const res = await fetch(`${API}/output/excel/${jobId}`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to download Excel");
  
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `packing_list_${jobId}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}

export interface MappedItem {
  field: string;
  value: string;
  label: string;
  is_canonical: boolean;
  is_confirmed?: boolean;
}

/** Get ALL extracted key→value pairs (for the drag-drop "All Mapped Fields" panel) */
export async function getAllCandidates(jobId: string): Promise<MappedItem[]> {
  const res = await fetch(`${API}/mapping/all_candidates/${jobId}`);
  if (!res.ok) throw new Error("Failed to fetch all candidates");
  const data = await res.json();
  return data.items as MappedItem[];
}
