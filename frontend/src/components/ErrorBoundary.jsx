import { Component } from "react";

/** Prevents a rendering bug from blanking the whole app. */
export default class ErrorBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="state state-error" role="alert" style={{ margin: "1.5rem" }}>
          <strong>This page failed to render.</strong> {String(this.state.error.message || this.state.error)}
        </div>
      );
    }
    return this.props.children;
  }
}
