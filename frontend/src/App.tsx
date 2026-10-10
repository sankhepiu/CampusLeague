import { BrowserRouter } from 'react-router-dom';
import { OptionsProvider } from './core/providers/OptionsProvider';
import { SoundProvider } from './core/providers/SoundProvider';
import { ToastProvider } from './core/providers/ToastProvider';
import { AuthProvider } from './core/providers/AuthProvider';
import { AchievementsProvider } from './core/providers/AchievementsProvider';
import { AppRoutes } from './core/routes/AppRoutes';

function App() {
  return (
    <>
      <div className="cl-backdrop" aria-hidden="true" />
      <BrowserRouter>
        <OptionsProvider>
          <SoundProvider>
            <ToastProvider>
              <AuthProvider>
                <AchievementsProvider>
                  <AppRoutes />
                </AchievementsProvider>
              </AuthProvider>
            </ToastProvider>
          </SoundProvider>
        </OptionsProvider>
      </BrowserRouter>
    </>
  );
}

export default App;
