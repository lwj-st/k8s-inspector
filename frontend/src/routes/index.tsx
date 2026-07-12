import { RouteObject } from "react-router-dom";

import { AppLayout } from "../layouts/AppLayout";
import { DiagnosisPage } from "../pages/DiagnosisPage";
import { NamespaceInspectionPage } from "../pages/NamespaceInspectionPage";
import { OverviewPage } from "../pages/OverviewPage";
import { PodInspectionPage } from "../pages/PodInspectionPage";
import { SettingsPage } from "../pages/SettingsPage";
import { TemplatesPage } from "../pages/TemplatesPage";
import { WhitelistsPage } from "../pages/WhitelistsPage";

export const appRoutes: RouteObject[] = [
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "inspections/namespace", element: <NamespaceInspectionPage /> },
      { path: "inspections/pod", element: <PodInspectionPage /> },
      { path: "diagnosis", element: <DiagnosisPage /> },
      { path: "templates", element: <TemplatesPage /> },
      { path: "whitelists", element: <WhitelistsPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
];
