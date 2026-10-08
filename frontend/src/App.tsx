import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import { RedirectIfAuthenticated, RequireAuth, RequireRole } from "./auth/guards";
import { AdminLayout } from "./components/AdminLayout";
import { Layout } from "./components/Layout";
import { AdminAnnouncementsPage } from "./pages/admin/AdminAnnouncementsPage";
import { AdminReviewsPage } from "./pages/admin/AdminReviewsPage";
import { AdminSupportPage } from "./pages/admin/AdminSupportPage";
import { AdminTransactionsPage } from "./pages/admin/AdminTransactionsPage";
import { AdminUsersPage } from "./pages/admin/AdminUsersPage";
import { AdminWebhooksPage } from "./pages/admin/AdminWebhooksPage";
import { ExchangePage } from "./pages/ExchangePage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { LoginPage } from "./pages/LoginPage";
import { MerchantPage } from "./pages/MerchantPage";
import { MerchantsPage } from "./pages/MerchantsPage";
import { NewsItemPage, NewsPage } from "./pages/NewsPage";
import { PayPage } from "./pages/PayPage";
import { ServicesPage } from "./pages/ServicesPage";
import { RegisterPage } from "./pages/RegisterPage";
import { RequestsPage } from "./pages/RequestsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StatsPage } from "./pages/StatsPage";
import { TransactionPage } from "./pages/TransactionPage";
import { TransactionsPage } from "./pages/TransactionsPage";
import { TransferPage } from "./pages/TransferPage";
import { WalletPage } from "./pages/WalletPage";
import { WalletsPage } from "./pages/WalletsPage";
import { createQueryClient } from "./queryClient";
import { useI18n } from "./i18n";

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
    <Routes>
      {/* Admin console (ADR-0005): a separate app with its own sign-in
          and layout. Nothing in the customer site links here. */}
      <Route path="admin/login" element={<RedirectIfAuthenticated home="/admin" />}>
        <Route index element={<LoginPage admin />} />
      </Route>
      <Route path="admin" element={<RequireAuth loginPath="/admin/login" />}>
        <Route element={<RequireRole roles={["SUPPORT", "ADMIN"]} />}>
          <Route element={<AdminLayout />}>
            <Route index element={<Navigate to="reviews" replace />} />
            <Route path="users" element={<AdminUsersPage />} />
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
