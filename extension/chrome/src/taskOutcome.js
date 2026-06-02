/**
 * 根据搜索 runner(runJdSearchTask / runZkhSearchTask)的返回,
 * 决定子任务最终状态。纯函数,不依赖 chrome / DOM,可被 node --test 单测。
 *
 * runner 结果形如:{ offers, error, loginRequired, searchTerm }
 * 返回:{ status: "done" | "login_required" | "failed", message }
 *
 * 关键点:补出 "login_required" 这条路径 —— 旧 background 只有 done/failed,
 * 导致震坤行未登录拿到的"订货编码"默认页要么被当 done 展示垃圾、要么被当
 * failed。现在 runner 判定为登录态问题时,统一落到 login_required,
 * message 携带后端 _is_heartbeat_login_error / 前端 isHeartbeatLoginRequired
 * 能识别的"登录态未知"标记,从而触发"请在扩展完成登录"的引导与后续重排。
 */
export function decideSubtaskOutcome(result) {
  const offers = Array.isArray(result?.offers) ? result.offers : [];
  if (offers.length > 0) {
    return { status: "done", message: "" };
  }
  if (result?.loginRequired) {
    return {
      status: "login_required",
      message: result?.error || "震坤行登录态未知,请在扩展完成登录后重试",
    };
  }
  if (result?.error) {
    return { status: "failed", message: result.error };
  }
  return { status: "failed", message: "未获取到搜索结果" };
}
