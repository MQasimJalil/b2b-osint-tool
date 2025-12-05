import React, { useState, useEffect } from 'react';
import { Plus, BarChart2, Mail, Loader2, Trash2 } from 'lucide-react';
import { api } from '../../api/client';
import { useToast } from '../ui/Toast';
import { ConfirmationModal } from '../ui/Modal';

export function CampaignList({ onSelectCampaign }) {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const { error, success } = useToast();
  const [deleteId, setDeleteId] = useState(null);

  const loadCampaigns = async () => {
    try {
      setLoading(true);
      const res = await api.campaigns.list();
      setCampaigns(res.data);
    } catch (err) {
      console.error(err);
      error("Failed to load campaigns");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCampaigns();
  }, []);

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await api.campaigns.delete(deleteId);
      success("Campaign deleted");
      loadCampaigns();
    } catch (err) {
      error("Failed to delete campaign");
    } finally {
      setDeleteId(null);
    }
  };

  if (loading) return <div className="p-8 text-center text-gray-500"><Loader2 className="w-8 h-8 animate-spin mx-auto mb-2"/>Loading campaigns...</div>;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">Email Campaigns</h2>
        <div className="flex gap-2">
          <button className="flex items-center px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50">
            <BarChart2 className="w-4 h-4 mr-2" /> Stats
          </button>
          <button 
            onClick={() => onSelectCampaign('new')}
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
          >
            <Plus className="w-4 h-4 mr-2" /> New Campaign
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {campaigns.map(campaign => (
          <div 
            key={campaign.id}
            className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow cursor-pointer relative group"
            onClick={() => onSelectCampaign(campaign)}
          >
            <div className="flex justify-between items-start mb-4">
              <div className="p-3 bg-blue-100 rounded-lg">
                <Mail className="w-6 h-6 text-blue-600" />
              </div>
              <div className="flex items-center gap-2">
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                  campaign.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                }`}>
                  {campaign.status.toUpperCase()}
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); setDeleteId(campaign.id); }}
                  className="p-1 text-gray-400 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Delete Campaign"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
            
            <h3 className="text-lg font-semibold text-gray-900 mb-1">{campaign.name}</h3>
            <p className="text-sm text-gray-500 mb-4">Created {new Date(campaign.created_at).toLocaleDateString()}</p>
            
            <div className="grid grid-cols-3 gap-2 border-t border-gray-100 pt-4">
              <div className="text-center">
                <p className="text-xs text-gray-500">Drafts</p>
                <p className="font-semibold text-gray-900">{campaign.stats?.emails_generated || 0}</p>
              </div>
              <div className="text-center border-l border-gray-100">
                <p className="text-xs text-gray-500">Sent</p>
                <p className="font-semibold text-gray-900">{campaign.stats?.emails_sent || 0}</p>
              </div>
              <div className="text-center border-l border-gray-100">
                <p className="text-xs text-gray-500">Opened</p>
                <p className="font-semibold text-gray-900">{campaign.stats?.emails_opened || 0}%</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      <ConfirmationModal
        isOpen={!!deleteId}
        onClose={() => setDeleteId(null)}
        onConfirm={handleDelete}
        title="Delete Campaign"
        message="Are you sure you want to delete this campaign? This action cannot be undone."
        confirmText="Delete"
        variant="danger"
      />
    </div>
  );
}
