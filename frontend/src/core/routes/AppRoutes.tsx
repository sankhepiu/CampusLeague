import { Navigate, Route, Routes } from 'react-router-dom';
import { StartScreen } from './StartScreen';
import { LoadingScreen } from './LoadingScreen';
import { HomePage } from './HomePage';
import { AppLayout } from './AppLayout';
import { ProtectedRoute } from './ProtectedRoute';
import { LoginPage } from '../../features/auth/LoginPage';
import { SignupPage } from '../../features/auth/SignupPage';
import { SettingsPage } from '../../features/settings/SettingsPage';
import { MembershipPage } from '../../features/membership/MembershipPage';
import { MemberCardPage } from '../../features/membership/MemberCardPage';
import { MembersPage } from '../../features/members/MembersPage';
import { EventsPage } from '../../features/events/EventsPage';
import { EventDetailPage } from '../../features/events/EventDetailPage';
import { EventAdminPage } from '../../features/events/EventAdminPage';
import { TicketsPage } from '../../features/tickets/TicketsPage';
import { ShopPage } from '../../features/shop/ShopPage';
import { ProductDetailPage } from '../../features/shop/ProductDetailPage';
import { CartPage } from '../../features/shop/CartPage';
import { ShopAdminPage } from '../../features/shop/ShopAdminPage';
import { OrdersPage } from '../../features/orders/OrdersPage';
import { VolunteeringPage } from '../../features/volunteering/VolunteeringPage';
import { FundraiserDetailPage } from '../../features/volunteering/FundraiserDetailPage';
import { FundraiserAdminPage } from '../../features/volunteering/FundraiserAdminPage';
import { AnnouncementsPage } from '../../features/announcements/AnnouncementsPage';
import { AnnouncementDetailPage } from '../../features/announcements/AnnouncementDetailPage';
import { AnnouncementComposerPage } from '../../features/announcements/AnnouncementComposerPage';
import { AnnouncementDeliveriesPage } from '../../features/announcements/AnnouncementDeliveriesPage';
import { CheckinPage } from '../../features/checkin/CheckinPage';
import { MyExpensesPage } from '../../features/expenses/MyExpensesPage';
import { ExpenseSubmitPage } from '../../features/expenses/ExpenseSubmitPage';
import { ExpenseApprovalPage } from '../../features/expenses/ExpenseApprovalPage';
import { FinancePage } from '../../features/finance/FinancePage';
import { LedgerPage } from '../../features/finance/LedgerPage';
import { InsightsPage } from '../../features/insights/InsightsPage';
import { AdminPage } from '../../features/admin/AdminPage';
import { FEATURE_ACCESS } from '../config/roles';

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<StartScreen />} />
      <Route path="/loading" element={<LoadingScreen />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />

      {/* Public per the contract (GET /events, GET /announcements — "Who:
          Public"). Still rendered inside AppLayout for a consistent
          header/footer; TopBar itself handles the logged-out case. */}
      <Route element={<AppLayout />}>
        <Route path="/events" element={<EventsPage />} />
        <Route path="/events/:id" element={<EventDetailPage />} />
        <Route path="/announcements" element={<AnnouncementsPage />} />
        <Route path="/announcements/:id" element={<AnnouncementDetailPage />} />
      </Route>

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/home" element={<HomePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/membership" element={<MembershipPage />} />
        <Route path="/membership/card" element={<MemberCardPage />} />
        <Route path="/tickets" element={<TicketsPage />} />
        <Route path="/shop" element={<ShopPage />} />
        <Route path="/shop/cart" element={<CartPage />} />
        <Route path="/shop/:id" element={<ProductDetailPage />} />
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/volunteering" element={<VolunteeringPage />} />
        <Route path="/volunteering/:id" element={<FundraiserDetailPage />} />

        <Route
          path="/volunteering/new"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.volunteerAdmin}>
              <FundraiserAdminPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/volunteering/:id/edit"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.volunteerAdmin}>
              <FundraiserAdminPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/events/new"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.eventAdmin}>
              <EventAdminPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/events/:id/edit"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.eventAdmin}>
              <EventAdminPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/shop/new"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.shopAdmin}>
              <ShopAdminPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/shop/:id/edit"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.shopAdmin}>
              <ShopAdminPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/announcements/new"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.announcementCompose}>
              <AnnouncementComposerPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/announcements/:id/deliveries"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.announcementCompose}>
              <AnnouncementDeliveriesPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/members"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.members}>
              <MembersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/checkin"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.checkin}>
              <CheckinPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/expenses"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.expenses}>
              <MyExpensesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/expenses/new"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.expenses}>
              <ExpenseSubmitPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/expenses/approvals"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.expenseApproval}>
              <ExpenseApprovalPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/finance"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.finance}>
              <FinancePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/finance/ledger"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.finance}>
              <LedgerPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/insights"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.insights}>
              <InsightsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute roles={FEATURE_ACCESS.admin}>
              <AdminPage />
            </ProtectedRoute>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
