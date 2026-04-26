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
  mfg_sku: string | null;
  l1_category_name: string | null;
  l2_category_name: string | null;
  l3_category_name: string | null;
  l4_category_name: string | null;
  attribute_details: string | null;
  files?: SkuFile[];
}

export interface CompetitorItem {
  name: string;
  price: string | null;
  unit: string | null;
  sku: string | null;
  url: string | null;
  delivery: string | null;
  source: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  imageUrl?: string;     // Data URL for display in user bubble
  skuResults?: SkuItem[];
  competitorResults?: CompetitorItem[];
  isStreaming?: boolean;
  thinkingStatus?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
}

export interface AuthUser {
  id: number;
  phone: string;
  nickname: string | null;
  user_id: string;     // external id used as user_id in chat/feedback requests
  auth_token: string;
}
