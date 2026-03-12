export interface SkuFile {
  file_name: string;
  file_url: string;
  file_type_label: string;
}

export interface SkuItem {
  item_code: string;
  item_name: string;
  brand_name: string | null;
  specification: string | null;
  unit: string | null;
  l1_category_name: string | null;
  l2_category_name: string | null;
  l3_category_name: string | null;
  l4_category_name: string | null;
  attribute_details: string | null;
  files?: SkuFile[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  skuResults?: SkuItem[];
  isStreaming?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
}
