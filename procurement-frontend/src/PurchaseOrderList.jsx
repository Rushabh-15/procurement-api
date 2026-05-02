import { useState, useEffect } from 'react';
import api from './api';

const STATUS_COLORS = {
  DRAFT:    '#888',
  APPROVED: '#1D9E75',
  CLOSED:   '#378ADD',
};

export default function PurchaseOrderList() {
  const [orders,    setOrders]    = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [statusFilter, setStatusFilter] = useState('');

  useEffect(() => {
    const fetch = async () => {
      setLoading(true);
      const params = statusFilter ? `?status=${statusFilter}` : '';
      const res = await api.get(`/api/purchase-orders/${params}`);
      setOrders(res.data.results);
      setLoading(false);
    };
    fetch();
  }, [statusFilter]);

  const handleApprove = async (id) => {
    await api.post(`/api/purchase-orders/${id}/approve/`);
    setStatusFilter('');  // refresh list
  };

  return (
    <div style={{ maxWidth: 800, margin: '32px auto', padding: '0 16px' }}>
      <h2>Purchase Orders</h2>
      <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ marginBottom: 16 }}>
        <option value="">All statuses</option>
        <option value="DRAFT">Draft</option>
        <option value="APPROVED">Approved</option>
        <option value="CLOSED">Closed</option>
      </select>

      {loading ? <p>Loading...</p> : orders.map(po => (
        <div key={po.id} style={{ border: '1px solid #eee', borderRadius: 8, padding: 16, marginBottom: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <strong>PO-{po.id} — {po.supplier_name}</strong>
            <span style={{ color: STATUS_COLORS[po.status], fontWeight: 500 }}>{po.status}</span>
          </div>
          <div style={{ marginTop: 4, color: '#666' }}>₹{po.total_amount}</div>
          {po.status === 'DRAFT' &&
            <button onClick={() => handleApprove(po.id)} style={{ marginTop: 8 }}>Approve</button>
          }
        </div>
      ))}
    </div>
  );
}