import { FieldTopNav } from '../components/FieldTopNav';
import { Wifi, SignalLow, WifiOff, RefreshCcw, Cloud } from 'lucide-react';
import { useAppContext } from '../contexts/AppContext';

export const FieldNetworkHelpScreen = () => {
  const { setNetworkStatus, networkStatus, showToast } = useAppContext();

  const handleSetNetwork = (status: any) => {
    setNetworkStatus(status);
    showToast(`Network mode changed to ${status}`);
  };

  return (
    <div className="pt-16 pb-24 px-4 md:px-10 max-w-4xl mx-auto w-full space-y-10">
      <FieldTopNav title="Network Status & Help" showBack={true} />
      
      <section className="mt-6">
        <h1 className="text-3xl font-bold text-primary mb-4">Network Help — Status & Help</h1>
        <p className="text-lg text-on-surface-variant max-w-2xl leading-relaxed">
          Connection state controls sync behavior. For urgent real-world issues, follow your organization's existing radio/phone protocol. ReliefQueue does not replace emergency services.
        </p>
      </section>

      <section className="p-6 bg-surface-variant rounded-xl border-2 border-outline-variant shadow-sm">
        <h2 className="text-xl font-bold mb-4 flex items-center gap-2"><Wifi size={24}/> Prototype Mode Controls</h2>
        <div className="flex gap-3 flex-wrap">
          <button onClick={() => handleSetNetwork('online')} className={`px-5 py-3 rounded-lg font-bold border-2 active:scale-95 transition-transform ${networkStatus === 'online' ? 'bg-primary text-on-primary border-primary' : 'bg-surface text-on-surface border-outline'}`}>Online</button>
          <button onClick={() => handleSetNetwork('slow')} className={`px-5 py-3 rounded-lg font-bold border-2 active:scale-95 transition-transform ${networkStatus === 'slow' ? 'bg-secondary-container text-on-secondary-container border-secondary' : 'bg-surface text-on-surface border-outline'}`}>Slow</button>
          <button onClick={() => handleSetNetwork('offline')} className={`px-5 py-3 rounded-lg font-bold border-2 active:scale-95 transition-transform ${networkStatus === 'offline' ? 'bg-secondary text-on-secondary border-secondary' : 'bg-surface text-on-surface border-outline'}`}>Offline</button>
          <button onClick={() => handleSetNetwork('syncing')} className={`px-5 py-3 rounded-lg font-bold border-2 active:scale-95 transition-transform ${networkStatus === 'syncing' ? 'bg-primary-container text-on-primary-container border-primary' : 'bg-surface text-on-surface border-outline'}`}>Syncing</button>
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-bold text-primary mb-6">Connection States</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* Online */}
          <div className="bg-surface-container rounded-xl border-2 border-outline-variant p-6 flex flex-col gap-4 shadow-sm">
            <h3 className="text-xl font-bold text-primary">Online</h3>
            <div className="bg-tertiary-container text-on-tertiary-container rounded-lg p-3 flex items-center justify-center w-full border-2 border-tertiary h-14">
              <Wifi size={28} />
            </div>
            <p className="text-base text-on-surface-variant font-bold leading-relaxed">Optimal connection state. Data is syncing in real-time. Background syncing is active, which may use slightly more battery.</p>
          </div>

          {/* Slow */}
          <div className="bg-surface-container rounded-xl border-2 border-outline-variant p-6 flex flex-col gap-4 shadow-sm">
            <h3 className="text-xl font-bold text-primary">Slow Connection</h3>
            <div className="bg-secondary-container text-on-secondary-container rounded-lg p-3 flex items-center justify-center w-full border-2 border-secondary h-14">
              <SignalLow size={28} />
            </div>
            <p className="text-base text-on-surface-variant font-bold leading-relaxed">Degraded connection. Critical data prioritized (like text updates). Image uploads are paused to conserve battery and bandwidth.</p>
          </div>

          {/* Offline */}
          <div className="bg-surface-container rounded-xl border-2 border-outline-variant p-6 flex flex-col gap-4 shadow-sm">
            <h3 className="text-xl font-bold text-primary">Offline</h3>
            <div className="bg-surface-variant text-on-surface-variant rounded-lg p-3 flex items-center justify-center w-full border-2 border-outline h-14">
              <WifiOff size={28} />
            </div>
            <p className="text-base text-on-surface-variant font-bold leading-relaxed">No connection. App operating in local-only mode. All changes are saved on your device and will sync automatically when reconnected.</p>
          </div>
          
          {/* Syncing */}
          <div className="bg-surface-container rounded-xl border-2 border-outline-variant p-6 flex flex-col gap-4 shadow-sm">
            <h3 className="text-xl font-bold text-primary">Syncing Data</h3>
            <div className="bg-primary-container text-on-primary-container rounded-lg p-3 flex items-center justify-center w-full border-2 border-primary h-14">
              <RefreshCcw size={28} className="animate-spin" />
            </div>
            <p className="text-base text-on-surface-variant font-bold leading-relaxed">Data is actively transferring to the server. Do not close the app while critical data is syncing to ensure complete records.</p>
          </div>

          {/* Up to Date */}
          <div className="bg-surface-container rounded-xl border-2 border-outline-variant p-6 flex flex-col gap-4 shadow-sm">
            <h3 className="text-xl font-bold text-primary">Up to Date</h3>
            <div className="bg-surface-container-high text-on-surface rounded-lg p-3 flex items-center justify-center w-full border-2 border-outline-variant h-14">
              <Cloud size={28} />
            </div>
            <p className="text-base text-on-surface-variant font-bold leading-relaxed">All local changes have been successfully saved to the server. It is safe to close the app, go offline, or switch tasks.</p>
          </div>
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-bold text-primary mb-6">Operations Protocol</h2>
        <div className="space-y-4">
          <div className="bg-surface-container rounded-xl border-2 border-outline-variant p-6 shadow-sm">
            <h3 className="text-xl font-bold text-primary mb-2">Local Mode Operations</h3>
            <p className="text-lg text-on-surface-variant font-bold leading-relaxed">When offline, continue logging cases and updates. The app stores all data locally. Do not log out or clear app data while offline.</p>
          </div>
          
          <div className="bg-surface-container rounded-xl border-2 border-outline-variant p-6 shadow-sm">
            <h3 className="text-xl font-bold text-primary mb-2">Priority Syncing</h3>
            <p className="text-lg text-on-surface-variant font-bold leading-relaxed">On slow connections, critical case updates are prioritized over images. Wait for the 'Up to Date' status before closing the app to ensure all data is saved.</p>
          </div>
        </div>
      </section>
    </div>
  );
};
