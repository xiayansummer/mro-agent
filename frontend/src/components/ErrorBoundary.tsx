import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** 自定义兜底 UI;不传则用默认内联提示 */
  fallback?: ReactNode;
  /** 仅用于控制台日志定位,不展示给用户 */
  label?: string;
  /**
   * 任一元素变化时清除错误态并重新渲染子树。
   * 流式场景必传(如 [message.content.length, isStreaming]):某个中间 chunk 的
   * 半截形状渲染抛错后,后续 chunk 把数据补全时能自动恢复,而非永久冻结在兜底 UI。
   */
  resetKeys?: ReadonlyArray<unknown>;
}

interface State {
  hasError: boolean;
}

/**
 * 渲染故障隔离边界。子树在 render 阶段抛出的任何异常都会在这里被捕获,
 * 显示一个局部兜底 UI,而不会把整棵 React 树卸载导致整页白屏。
 *
 * 用法:逐条消息包裹(ChatWindow),单条结果渲染异常只影响那一条,
 * 其余消息与整体可用性不受影响;再在入口(main.tsx)套一层做最后兜底。
 * 流式内容传 resetKeys 让瞬时错误可自愈。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidUpdate(prevProps: Props): void {
    // resetKeys 变化(如流式 content 增长)时,清除错误态重新尝试渲染子树。
    if (this.state.hasError && !sameKeys(prevProps.resetKeys, this.props.resetKeys)) {
      this.setState({ hasError: false });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 保留到控制台便于线上定位;不上报、不阻塞渲染
    console.error(
      `[ErrorBoundary]${this.props.label ? " " + this.props.label : ""}`,
      error,
      info.componentStack,
    );
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return this.props.fallback ?? <div style={fallbackStyle}>⚠ 此条内容渲染异常,已跳过(其余内容不受影响)</div>;
    }
    return this.props.children;
  }
}

function sameKeys(a?: ReadonlyArray<unknown>, b?: ReadonlyArray<unknown>): boolean {
  if (a === b) return true;
  if (!a || !b || a.length !== b.length) return false;
  return a.every((v, i) => Object.is(v, b[i]));
}

const fallbackStyle = {
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "10px 14px",
  margin: "8px 0",
  background: "var(--surface)",
  color: "var(--text-muted)",
  fontSize: 13,
} as const;
