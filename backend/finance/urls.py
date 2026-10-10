from django.urls import path

from . import views

# Mounted at /api/.
urlpatterns = [
    path('expenses', views.ExpenseListCreateView.as_view(), name='expense-list'),
    path('expenses/me', views.MyExpensesView.as_view(), name='expense-me'),
    path('expenses/<int:pk>/approve', views.ExpenseDecisionView.as_view(action='approve'), name='expense-approve'),
    path('expenses/<int:pk>/reject', views.ExpenseDecisionView.as_view(action='reject'), name='expense-reject'),
    path('expenses/<int:pk>/mark-paid', views.ExpenseDecisionView.as_view(action='mark_paid'), name='expense-mark-paid'),
    path('finance/summary', views.SummaryView.as_view(), name='finance-summary'),
    path('finance/ledger', views.LedgerListView.as_view(), name='finance-ledger'),
    path('finance/reconcile', views.ReconcileView.as_view(), name='finance-reconcile'),
    path('finance/trace', views.TraceView.as_view(), name='finance-trace'),
]
