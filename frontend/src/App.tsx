import React, { useState, useEffect } from "react";
import { Dashboard } from "./pages/Dashboard";
import { ChainingApproval } from "./pages/ChainingApproval";
import { NetworkApproval } from "./pages/NetworkApproval";
import { AdminConfig } from "./pages/AdminConfig";

export const App: React.FC = () => {
  const [route, setRoute] = useState(() => window.location.hash.replace("#", "") || "/");

  useEffect(() => {
    const handleHashChange = () => {
      setRoute(window.location.hash.replace("#", "") || "/");
    };
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  if (route.startsWith("/chaining")) {
    return <ChainingApproval />;
  } else if (route.startsWith("/network")) {
    return <NetworkApproval />;
  } else if (route.startsWith("/admin")) {
    return <AdminConfig />;
  } else {
    return <Dashboard />;
  }
};

export default App;
