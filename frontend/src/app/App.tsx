import { RouterProvider, createBrowserRouter } from "react-router-dom";

import { appConfig } from "./config";
import { appRoutes } from "../routes";

const router = createBrowserRouter(appRoutes, {
  basename: appConfig.routerBasename,
});

export function App() {
  return <RouterProvider router={router} />;
}
