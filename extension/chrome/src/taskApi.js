export async function fetchNextTask(apiBase, extToken) {
  const response = await fetch(`${apiBase}/extension/tasks/next`, {
    method: "GET",
    headers: { "X-Extension-Token": extToken },
  });
  if (response.status === 204) return null;
  if (!response.ok) {
    const detail = await safeDetail(response);
    throw new Error(detail || `拉取任务失败：${response.status}`);
  }
  return response.json();
}

export async function updateSubtaskStatus(apiBase, extToken, subtaskId, status, message = "") {
  const response = await fetch(`${apiBase}/extension/subtasks/${subtaskId}/status`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Extension-Token": extToken,
    },
    body: JSON.stringify({ status, message }),
  });
  if (!response.ok) {
    const detail = await safeDetail(response);
    throw new Error(detail || `更新任务状态失败：${response.status}`);
  }
  return response.json();
}

export async function submitSubtaskResults(apiBase, extToken, subtaskId, platform, searchTerm, offers) {
  const response = await fetch(`${apiBase}/extension/subtasks/${subtaskId}/results`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Extension-Token": extToken,
    },
    body: JSON.stringify({
      platform,
      searchTerm,
      offers,
    }),
  });
  if (!response.ok) {
    const detail = await safeDetail(response);
    throw new Error(detail || `回写任务结果失败：${response.status}`);
  }
  return response.json();
}

async function safeDetail(response) {
  try {
    const body = await response.json();
    return body.detail || body.message || "";
  } catch {
    return "";
  }
}
