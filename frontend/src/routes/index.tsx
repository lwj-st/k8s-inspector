import { RouteObject } from "react-router-dom";

import { AppLayout } from "../layouts/AppLayout";
import { AutoInspectionPage } from "../pages/AutoInspectionPage";
import { DiagnosisPage } from "../pages/DiagnosisPage";
import { NamespaceInspectionPage } from "../pages/NamespaceInspectionPage";
import { SettingsPage } from "../pages/SettingsPage";
import { TemplatesPage } from "../pages/TemplatesPage";
import { WhitelistsPage } from "../pages/WhitelistsPage";

export const appRoutes: RouteObject[] = [
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <AutoInspectionPage /> },
      { path: "inspections/namespace", element: <NamespaceInspectionPage /> },
      { path: "inspections/pod", element: <NamespaceInspectionPage /> },
      { path: "diagnosis", element: <DiagnosisPage /> },
      { path: "templates", element: <TemplatesPage /> },
      { path: "whitelists", element: <WhitelistsPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
];
