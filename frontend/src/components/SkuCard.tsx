import { SkuItem } from "../types";

interface Props {
  sku: SkuItem;
  index: number;
}

export default function SkuCard({ sku, index }: Props) {
  // Parse attribute_details (pipe-separated key:value pairs)
  const attributes = parseAttributes(sku.attribute_details);

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-2">
        <span className="text-xs font-mono text-gray-400">#{index + 1}</span>
        <span className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded">
          {sku.item_code}
        </span>
      </div>

      <h4 className="text-sm font-medium text-gray-900 mb-2 leading-snug line-clamp-2">
        {sku.item_name}
      </h4>

      <div className="space-y-1 text-xs text-gray-500">
        {sku.brand_name && (
          <div className="flex">
            <span className="w-12 shrink-0 text-gray-400">品牌</span>
            <span className="text-gray-700 font-medium">{sku.brand_name}</span>
          </div>
        )}
        <div className="flex">
          <span className="w-12 shrink-0 text-gray-400">分类</span>
          <span className="text-gray-600">
            {[sku.l2_category_name, sku.l3_category_name, sku.l4_category_name]
              .filter(Boolean)
              .join(" > ")}
          </span>
        </div>
        {sku.specification && (
          <div className="flex">
            <span className="w-12 shrink-0 text-gray-400">规格</span>
            <span className="text-gray-600">{sku.specification}</span>
          </div>
        )}
        {sku.unit && (
          <div className="flex">
            <span className="w-12 shrink-0 text-gray-400">单位</span>
            <span className="text-gray-600">{sku.unit}</span>
          </div>
        )}
      </div>

      {attributes.length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-100">
          <div className="flex flex-wrap gap-1">
            {attributes.slice(0, 4).map((attr, i) => (
              <span
                key={i}
                className="text-xs bg-gray-50 text-gray-600 px-1.5 py-0.5 rounded"
              >
                {attr.key}: {attr.value}
              </span>
            ))}
            {attributes.length > 4 && (
              <span className="text-xs text-gray-400">
                +{attributes.length - 4}
              </span>
            )}
          </div>
        </div>
      )}

      {sku.files && sku.files.length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-100">
          <div className="flex flex-wrap gap-1.5">
            {sku.files.map((file, i) => (
              <a
                key={i}
                href={file.file_url}
                target="_blank"
                rel="noopener noreferrer"
                className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded hover:opacity-80 transition-opacity ${getFileTypeStyle(file.file_type_label)}`}
                title={file.file_name}
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
                {file.file_type_label}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function getFileTypeStyle(label: string): string {
  switch (label) {
    case "认证证书":
      return "bg-green-50 text-green-700";
    case "技术资料":
      return "bg-blue-50 text-blue-700";
    case "检测报告":
      return "bg-orange-50 text-orange-700";
    case "相关文档":
      return "bg-purple-50 text-purple-700";
    default:
      return "bg-gray-50 text-gray-600";
  }
}

function parseAttributes(
  details: string | null
): { key: string; value: string }[] {
  if (!details) return [];
  return details
    .split("|")
    .map((pair) => {
      const [key, value] = pair.split(":");
      return key && value ? { key: key.trim(), value: value.trim() } : null;
    })
    .filter((x): x is { key: string; value: string } => x !== null);
}
