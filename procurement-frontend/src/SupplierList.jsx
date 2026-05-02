// src/SupplierList.jsx
import { useState, useEffect } from 'react';
import api from './api';

export default function SupplierList() {
  const [suppliers, setSuppliers] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState('');
  const [page,      setPage]      = useState(1);
  const [totalCount,setTotalCount]= useState(0);
  const [newName,   setNewName]   = useState('');
  const [newEmail,  setNewEmail]  = useState('');

  // useEffect: fetch suppliers whenever 'page' changes
  useEffect(() => {
    const fetchSuppliers = async () => {
      setLoading(true);
      try {
        const res = await api.get(`/api/suppliers/?page=${page}`);
        setSuppliers(res.data.results);
        setTotalCount(res.data.count);
      } catch {
        setError('Failed to load suppliers. Check your token.');
      } finally {
        setLoading(false);
      }
    };
    fetchSuppliers();
  }, [page]);  // re-run when page changes

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      await api.post('/api/suppliers/', { name: newName, email: newEmail });
      setNewName(''); setNewEmail('');
      setPage(1);   // go back to page 1 to see the new entry
    } catch (err) {
      setError(err.response?.data?.email?.[0] || 'Failed to create supplier.');
    }
  };

  if (loading) return <p>Loading...</p>;
  if (error)   return <p style={{ color: 'red' }}>{error}</p>;

  return (
    <div style={{ maxWidth: 700, margin: '32px auto', padding: '0 16px' }}>
      <h2>Suppliers ({totalCount} total)</h2>

      <form onSubmit={handleCreate} style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <input placeholder="Name" value={newName}  onChange={e => setNewName(e.target.value)}  required />
        <input placeholder="Email" value={newEmail} onChange={e => setNewEmail(e.target.value)} required />
        <button type="submit">Add Supplier</button>
      </form>

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>{['ID','Name','Email','Verified'].map(h =>
            <th key={h} style={{ textAlign:'left', padding:'8px', borderBottom:'2px solid #eee' }}>{h}</th>
          )}</tr>
        </thead>
        <tbody>
          {suppliers.map(s => (
            <tr key={s.id}>
              <td style={{ padding: '8px', borderBottom: '1px solid #eee' }}>{s.id}</td>
              <td style={{ padding: '8px', borderBottom: '1px solid #eee' }}>{s.name}</td>
              <td style={{ padding: '8px', borderBottom: '1px solid #eee' }}>{s.email}</td>
              <td style={{ padding: '8px', borderBottom: '1px solid #eee' }}>
                {s.is_verified ? '✓' : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
        <button onClick={() => setPage(p => p - 1)} disabled={page === 1}>← Prev</button>
        <span>Page {page}</span>
        <button onClick={() => setPage(p => p + 1)} disabled={suppliers.length < 10}>Next →</button>
      </div>
    </div>
  );
}