// src/App.jsx
import { useState } from 'react';
import Login from './Login';
import SupplierList from './SupplierList';
import PurchaseOrderList from './PurchaseOrderList'; // ✅ missing import

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(
    !!localStorage.getItem('access_token')
  );

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setIsLoggedIn(false);
  };

  const [tab, setTab] = useState('suppliers'); // ✅ tab state

  if (!isLoggedIn) return <Login onLogin={() => setIsLoggedIn(true)} />;

  return (
    <div>
      {/* Top Navbar */}
      <div
        style={{
          padding: '12px 32px',
          borderBottom: '1px solid #eee',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <strong>Procurement Dashboard</strong>
        <button onClick={handleLogout}>Logout</button>
      </div>

      {/* ✅ Tab Switcher */}
      <div
        style={{
          padding: '0 32px',
          borderBottom: '1px solid #eee',
          display: 'flex',
          gap: 16,
        }}
      >
        <button
          onClick={() => setTab('suppliers')}
          style={{ fontWeight: tab === 'suppliers' ? 700 : 400 }}
        >
          Suppliers
        </button>

        <button
          onClick={() => setTab('orders')}
          style={{ fontWeight: tab === 'orders' ? 700 : 400 }}
        >
          Purchase Orders
        </button>
      </div>

      {/* ✅ Conditional Rendering */}
      {tab === 'suppliers' ? <SupplierList /> : <PurchaseOrderList />}
    </div>
  );
}