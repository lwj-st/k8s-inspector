import { RouteObject } from "react-router-dom";

import { AppLayout } from "../layouts/AppLayout";
import { RequireSession, SessionProvider } from "../features/auth/SessionContext";
import { AutoInspectionPage } from "../pages/AutoInspectionPage";
import { DiagnosisPage } from "../pages/DiagnosisPage";
import { IssueDetailPage } from "../pages/IssueDetailPage";
import { LoginPage } from "../pages/LoginPage";
import { LogRecordingsPage } from "../pages/LogRecordingsPage";
import { NamespaceInspectionPage } from "../pages/NamespaceInspectionPage";
import { PodInspectionPage } from "../pages/PodInspectionPage";
import { ProblemWorkbenchPage } from "../pages/ProblemWorkbenchPage";
import { SettingsPage } from "../pages/SettingsPage";
import { TemplatesPage } from "../pages/TemplatesPage";
import { WhitelistsPage } from "../pages/WhitelistsPage";

export const appRoutes: RouteObject[] = [
  {
    element: <SessionProvider />,
    children: [
      { path: "/login", element: <LoginPage /> },
      {
        element: <RequireSession />,
        children: [
          {
            path: "/",
            element: <AppLayout />,
            children: [
              { index: true, element: <ProblemWorkbenchPage /> },
              { path: "issues/:id", element: <IssueDetailPage /> },
              { path: "inspections/status", element: <AutoInspectionPage /> },
              { path: "inspections/namespace", element: <NamespaceInspectionPage /> },
              { path: "inspections/pod", element: <PodInspectionPage initialScopeMode="single" /> },
              { path: "log-recordings", element: <LogRecordingsPage /> },
              { path: "diagnosis", element: <DiagnosisPage /> },
              { path: "templates", element: <TemplatesPage /> },
              { path: "whitelists", element: <WhitelistsPage /> },
              { path: "settings", element: <SettingsPage /> },
            ],
          },
        ],
      },
    ],
  },
];
