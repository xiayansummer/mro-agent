import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** 自定义兜底 UI;不传则用默认内联提示 */
  fallback?: ReactNode;
  /** 仅用于控制台日志定位,不展示给用户 */
  label?: string;
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
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
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

const fallbackStyle = {
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "10px 14px",
  margin: "8px 0",
  background: "var(--surface)",
  color: "var(--text-muted)",
  fontSize: 13,
} as const;
