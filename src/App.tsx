import "./App.css";
import { AppProvider, useApp } from "./store/AppContext";
import Landing from "./components/Landing";
import Login from "./components/Login";
import ConfirmScreen from "./components/ConfirmScreen";
import BuildScreen from "./components/BuildScreen";
import StackReady from "./components/StackReady";
import Dashboard from "./components/Dashboard";

function Router() {
  const { project, building, analyzing, preview, analyzeError, justBuilt, newBuild } =
    useApp();
  if (building) return <BuildScreen />;
  if (analyzing || preview || analyzeError) return <ConfirmScreen />;
  // Build complete, but isolate from the workspace until the user confirms.
  if (project && justBuilt) return <StackReady />;
  if (project) return <Dashboard />;
  // Building a brand-new stack (chosen at the brand step, post-login).
  if (newBuild) return <Landing />;
  // Entry point: Brand (select/add) → Role. Login handles auth internally.
  return <Login />;
}

export default function App() {
  return (
    <AppProvider>
      <Router />
    </AppProvider>
  );
}
