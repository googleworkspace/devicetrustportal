/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
