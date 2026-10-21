import { QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense, useState, type ComponentType } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import { RedirectIfAuthenticated, RequireAuth, RequireRole } from "./auth/guards";
import { Layout } from "./components/Layout";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { TransferPage } from "./pages/TransferPage";
import { WalletsPage } from "./pages/WalletsPage";
import { createQueryClient } from "./queryClient";
import { PageSkeleton } from "./components/Skeleton";
import { useI18n } from "./i18n";

/** A page loaded the first time it is opened, not with the app: the
 * customer who never opens Merchants or Statistics never downloads them,
 * and nobody but staff downloads the admin console. The few pages almost
 * every visit starts on stay in the main bundle. */
function later<K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) {
  return lazy(() => load().then((module) => ({ default: module[name] })));
}

const AdminLayout = later(() => import("./components/AdminLayout"), "AdminLayout");
const AdminAnnouncementsPage = later(() => import("./pages/admin/AdminAnnouncementsPage"), "AdminAnnouncementsPage");
const AdminDashboardPage = later(() => import("./pages/admin/AdminDashboardPage"), "AdminDashboardPage");
const AdminReviewsPage = later(() => import("./pages/admin/AdminReviewsPage"), "AdminReviewsPage");
const AdminUserPage = later(() => import("./pages/admin/AdminUserPage"), "AdminUserPage");
const AdminSupportPage = later(() => import("./pages/admin/AdminSupportPage"), "AdminSupportPage");
const AdminTransactionsPage = later(() => import("./pages/admin/AdminTransactionsPage"), "AdminTransactionsPage");
const AdminUsersPage = later(() => import("./pages/admin/AdminUsersPage"), "AdminUsersPage");
const AdminWebhooksPage = later(() => import("./pages/admin/AdminWebhooksPage"), "AdminWebhooksPage");
const ExchangePage = later(() => import("./pages/ExchangePage"), "ExchangePage");
const MerchantPage = later(() => import("./pages/MerchantPage"), "MerchantPage");
const MerchantsPage = later(() => import("./pages/MerchantsPage"), "MerchantsPage");
const NewsItemPage = later(() => import("./pages/NewsPage"), "NewsItemPage");
const NewsPage = later(() => import("./pages/NewsPage"), "NewsPage");
const PayPage = later(() => import("./pages/PayPage"), "PayPage");
const ServicesPage = later(() => import("./pages/ServicesPage"), "ServicesPage");
const AutopayPage = later(() => import("./pages/AutopayPage"), "AutopayPage");
const GoalsPage = later(() => import("./pages/GoalsPage"), "GoalsPage");
const TemplatesPage = later(() => import("./pages/TemplatesPage"), "TemplatesPage");
const RequestsPage = later(() => import("./pages/RequestsPage"), "RequestsPage");
const SettingsPage = later(() => import("./pages/SettingsPage"), "SettingsPage");
const StatsPage = later(() => import("./pages/StatsPage"), "StatsPage");
const TransactionPage = later(() => import("./pages/TransactionPage"), "TransactionPage");
const TransactionsPage = later(() => import("./pages/TransactionsPage"), "TransactionsPage");
const WalletPage = later(() => import("./pages/WalletPage"), "WalletPage");

function NotFound() {
  const { t } = useI18n();
  return (
    <section className="page">
      <h1>{t("shell.notFound.title")}</h1>
      <Link to="/">{t("shell.notFound.back")}</Link>
    </section>
  );
}

export function AppRoutes() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        {/* Admin console (ADR-0005): a separate app with its own sign-in
            and layout. Nothing in the customer site links here. */}
        <Route path="admin/login" element={<RedirectIfAuthenticated home="/admin" />}>
          <Route index element={<LoginPage admin />} />
        </Route>
        <Route path="admin" element={<RequireAuth loginPath="/admin/login" />}>
          <Route element={<RequireRole roles={["SUPPORT", "ADMIN"]} />}>
            <Route element={<AdminLayout />}>
              <Route index element={<AdminDashboardPage />} />
              <Route path="users" element={<AdminUsersPage />} />
              <Route path="users/:userId" element={<AdminUserPage />} />
              <Route path="reviews" element={<AdminReviewsPage />} />
              <Route path="transactions" element={<AdminTransactionsPage />} />
              <Route path="webhooks" element={<AdminWebhooksPage />} />
              <Route path="announcements" element={<AdminAnnouncementsPage />} />
              <Route path="support" element={<AdminSupportPage />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Route>
        </Route>

        {/* Customer site. */}
        <Route element={<RedirectIfAuthenticated />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        </Route>
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            <Route index element={<WalletsPage />} />
            <Route path="wallets/:walletId" element={<WalletPage />} />
            <Route path="transfer" element={<TransferPage />} />
            <Route path="pay" element={<ServicesPage />} />
            <Route path="templates" element={<TemplatesPage />} />
            <Route path="autopay" element={<AutopayPage />} />
            <Route path="goals" element={<GoalsPage />} />
            <Route path="pay/merchant" element={<PayPage />} />
            <Route path="transactions" element={<TransactionsPage />} />
            <Route path="transactions/:transactionId" element={<TransactionPage />} />
            <Route path="merchants" element={<MerchantsPage />} />
            <Route path="merchants/:merchantId" element={<MerchantPage />} />
            <Route path="exchange" element={<ExchangePage />} />
            <Route path="stats" element={<StatsPage />} />
            <Route path="requests" element={<RequestsPage />} />
            <Route path="news" element={<NewsPage />} />
            <Route path="news/:newsId" element={<NewsItemPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  );
}

export function App() {
  const [queryClient] = useState(createQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
