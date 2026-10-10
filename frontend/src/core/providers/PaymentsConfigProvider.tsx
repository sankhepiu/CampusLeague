import { createContext, useEffect, useState, type ReactNode } from 'react';
import { paymentsApi, type PaymentGateway } from '../../features/payments/api';

interface PaymentsConfigValue {
  gateway: PaymentGateway;
  loaded: boolean;
}

export const PaymentsConfigContext = createContext<PaymentsConfigValue | null>(null);

/** Fetched once, on app load, per the brief — not per checkout screen.
 * Defaults to 'mock' until it resolves (and if the request fails), which is
 * also the safe fallback: the familiar Test Mode screen, never a Razorpay
 * button flashing up before we actually know a gateway is configured. */
export function PaymentsConfigProvider({ children }: { children: ReactNode }) {
  const [value, setValue] = useState<PaymentsConfigValue>({ gateway: 'mock', loaded: false });

  useEffect(() => {
    let cancelled = false;
    paymentsApi
      .getConfig()
      .then((config) => {
        if (!cancelled) setValue({ gateway: config.gateway, loaded: true });
      })
      .catch(() => {
        if (!cancelled) setValue({ gateway: 'mock', loaded: true });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return <PaymentsConfigContext.Provider value={value}>{children}</PaymentsConfigContext.Provider>;
}
