import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { CampaignList } from '../components/email/CampaignList';
import { ArrowLeft, Loader2, Mail, Eye, Send, RotateCw, Plus, X, Search, CheckCircle2 } from 'lucide-react';
import { api } from '../api/client';
import { useToast } from '../components/ui/Toast';
import { PromptModal } from '../components/ui/Modal';

// --- Add Companies Modal ---
function AddCompaniesModal({ isOpen, onClose, onAdd, campaignId }) {
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    if (isOpen) {
      loadCompanies();
    }
  }, [isOpen]);

  const loadCompanies = async () => {
    setLoading(true);
    try {
      // Only fetch companies with embedded data suitable for AI generation
      const res = await api.companies.list({ only_embedded: true, limit: 100 });
      setCompanies(res.data.companies || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (id) => {
    const newSet = new Set(selected);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelected(newSet);
  };

  const handleAdd = () => {
    onAdd(Array.from(selected));
  };

  if (!isOpen) return null;

  const filteredCompanies = companies.filter(c => 
    c.domain.toLowerCase().includes(searchTerm.toLowerCase()) || 
    (c.company_name && c.company_name.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
      <div className="bg-white w-full max-w-2xl h-[80vh] rounded-lg shadow-xl flex flex-col animate-fade-in">
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h3 className="text-lg font-bold text-gray-900">Add Companies to Campaign</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500" /></button>
        </div>
        
        <div className="p-4 border-b border-gray-200">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input 
              type="text" 
              placeholder="Search companies..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="text-center py-8"><Loader2 className="w-8 h-8 animate-spin mx-auto text-blue-500" /></div>
          ) : filteredCompanies.length === 0 ? (
            <div className="text-center py-8 text-gray-500">No embedded companies found. Try crawling and embedding some first.</div>
          ) : (
            <div className="space-y-2">
              {filteredCompanies.map(c => (
                <div 
                  key={c.id}
                  onClick={() => toggleSelect(c.id)}
                  className={`flex items-center p-3 rounded-lg border cursor-pointer transition-colors ${
                    selected.has(c.id) ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <div className={`w-5 h-5 rounded border mr-3 flex items-center justify-center ${
                    selected.has(c.id) ? 'bg-blue-500 border-blue-500' : 'border-gray-300'
                  }`}>
                    {selected.has(c.id) && <CheckCircle2 className="w-3.5 h-3.5 text-white" />}
                  </div>
                  <div>
                    <p className="font-medium text-gray-900">{c.company_name || c.domain}</p>
                    <p className="text-xs text-gray-500">{c.domain}</p>
                    {c.description && (
                      <p className="text-xs text-gray-400 mt-0.5 line-clamp-1">{c.description}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200">Cancel</button>
          <button 
            onClick={handleAdd}
            disabled={selected.size === 0}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            Add {selected.size} Companies
          </button>
        </div>
      </div>
    </div>
  );
}

export default function EmailCenter() {
  const navigate = useNavigate();
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [loadingDrafts, setLoadingDrafts] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedDrafts, setSelectedDrafts] = useState(new Set());
  const { success, error } = useToast();

  // Load drafts when a campaign is selected
  useEffect(() => {
    if (selectedCampaign && selectedCampaign !== 'new') {
      loadDrafts(selectedCampaign.id);
    }
  }, [selectedCampaign]);

  // Auto-poll for updates if any draft is generating
  useEffect(() => {
    if (!drafts.some(d => d.status === 'generating')) return;
    
    const interval = setInterval(() => {
      if (selectedCampaign && selectedCampaign !== 'new') {
        // Silent reload (don't set global loading state to avoid flicker)
        api.campaigns.listDrafts(selectedCampaign.id).then(res => {
          setDrafts(res.data);
        }).catch(console.error);
      }
    }, 5000);
    
    return () => clearInterval(interval);
  }, [drafts, selectedCampaign]);

  const loadDrafts = async (campaignId) => {
    try {
      setLoadingDrafts(true);
      const res = await api.campaigns.listDrafts(campaignId);
      setDrafts(res.data);
      setSelectedDrafts(new Set()); // Clear selection on load
    } catch (err) {
      console.error(err);
      error("Failed to load drafts");
    } finally {
      setLoadingDrafts(false);
    }
  };

  const handleCreateCampaign = () => {
    setShowCreateModal(true);
  };

  const confirmCreateCampaign = async (name) => {
    try {
      const res = await api.campaigns.create({ name, status: 'active' });
      success("Campaign created");
      setSelectedCampaign(res.data);
      setShowCreateModal(false);
    } catch (err) {
      error("Failed to create campaign");
    }
  };

  const handleAddLeads = async (companyIds) => {
    try {
      setShowAddModal(false);
      // Trigger creation (which now sets status to 'uninitiated')
      await api.campaigns.generateDrafts(selectedCampaign.id, companyIds);
      success(`Added ${companyIds.length} companies to campaign`);
      // Reload drafts
      setTimeout(() => loadDrafts(selectedCampaign.id), 1000);
    } catch (err) {
      console.error(err);
      error("Failed to add leads");
    }
  };

  const handleToggleDraft = (id) => {
    const newSet = new Set(selectedDrafts);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedDrafts(newSet);
  };

  const handleSelectAll = () => {
    if (selectedDrafts.size === drafts.length) {
      setSelectedDrafts(new Set());
    } else {
      setSelectedDrafts(new Set(drafts.map(d => d.id)));
    }
  };

  const handleGenerateSelected = async () => {
    if (selectedDrafts.size === 0) return;
    try {
      await api.campaigns.generateSelected(selectedCampaign.id, Array.from(selectedDrafts));
      success(`Started generating emails for ${selectedDrafts.size} drafts`);
      setSelectedDrafts(new Set());
      loadDrafts(selectedCampaign.id);
    } catch (err) {
      console.error(err);
      error("Failed to start generation");
    }
  };

  return (
    <div className="max-w-7xl mx-auto">
      {/* 1. Campaign List View */}
      {!selectedCampaign ? (
        <CampaignList onSelectCampaign={(c) => c === 'new' ? handleCreateCampaign() : setSelectedCampaign(c)} />
      ) : (
        /* 2. Campaign Detail View */
        <div className="space-y-6">
          {/* Header */}
          <div>
            <button 
              onClick={() => setSelectedCampaign(null)}
              className="flex items-center text-sm text-gray-600 hover:text-gray-900 mb-4"
            >
              <ArrowLeft className="w-4 h-4 mr-1" /> Back to Campaigns
            </button>
            <div className="flex justify-between items-start">
              <div>
                <h1 className="text-3xl font-bold text-gray-900">{selectedCampaign.name}</h1>
                <p className="text-gray-500 mt-1">
                  {drafts.length} Recipients • Created {new Date(selectedCampaign.created_at).toLocaleDateString()}
                </p>
              </div>
              <div className="flex gap-2">
                <button 
                  onClick={() => loadDrafts(selectedCampaign.id)}
                  className="flex items-center px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50"
                >
                  <RotateCw className="w-4 h-4 mr-2" /> Refresh
                </button>
                <button 
                  onClick={() => setShowAddModal(true)}
                  className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
                >
                  <Plus className="w-4 h-4 mr-2" /> Add Leads
                </button>
              </div>
            </div>
          </div>

          {/* Drafts Table */}
          <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 bg-gray-50 flex justify-between items-center">
              <h3 className="font-semibold text-gray-900">Outreach List</h3>
              <div className="flex gap-2">
                <button 
                  onClick={handleGenerateSelected}
                  disabled={selectedDrafts.size === 0}
                  className="text-sm text-blue-600 font-medium hover:underline disabled:text-gray-400 disabled:no-underline"
                >
                  Generate Selected ({selectedDrafts.size})
                </button>
                <span className="text-gray-300">|</span>
                <button className="text-sm text-blue-600 font-medium hover:underline">Send All Ready</button>
              </div>
            </div>
            
            {loadingDrafts ? (
              <div className="p-12 text-center text-gray-500">
                <Loader2 className="w-8 h-8 animate-spin mx-auto mb-2" />
                Loading drafts...
              </div>
            ) : drafts.length === 0 ? (
              <div className="p-12 text-center text-gray-500">
                <Mail className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p>No emails in this campaign yet.</p>
                <button 
                  onClick={() => setShowAddModal(true)}
                  className="mt-4 px-4 py-2 text-sm text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-50"
                >
                  Add companies to campaign
                </button>
              </div>
            ) : (
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left">
                      <input 
                        type="checkbox" 
                        checked={drafts.length > 0 && selectedDrafts.size === drafts.length}
                        onChange={handleSelectAll}
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Company</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Subject</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {drafts.map((draft) => (
                    <tr key={draft.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4">
                        <input 
                          type="checkbox"
                          checked={selectedDrafts.has(draft.id)}
                          onChange={() => handleToggleDraft(draft.id)}
                          className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-medium text-gray-900">{draft.domain}</div>
                        <div className="text-xs text-gray-500">{draft.to_emails?.[0]}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          draft.status === 'ready' ? 'bg-green-100 text-green-800' :
                          draft.status === 'sent' ? 'bg-blue-100 text-blue-800' :
                          draft.status === 'generating' ? 'bg-amber-100 text-amber-800' :
                          'bg-gray-100 text-gray-600'
                        }`}>
                          {draft.status === 'generating' && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
                          {draft.status === 'uninitiated' ? 'draft' : draft.status}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className={`text-sm max-w-xs truncate ${!draft.subject ? 'text-gray-400 italic' : 'text-gray-900'}`}>
                          {draft.subject || 'Not generated yet'}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <button 
                          onClick={() => navigate(`/email/${selectedCampaign.id}/draft/${draft.id}`)}
                          className="text-gray-400 hover:text-blue-600 mr-3"
                          title="Edit / View"
                        >
                          <Eye className="w-5 h-5" />
                        </button>
                        <button 
                          className="text-gray-400 hover:text-green-600"
                          title="Send"
                        >
                          <Send className="w-5 h-5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Add Companies Modal */}
      <AddCompaniesModal 
        isOpen={showAddModal} 
        onClose={() => setShowAddModal(false)}
        onAdd={handleAddLeads}
        campaignId={selectedCampaign?.id}
      />

      <PromptModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onConfirm={confirmCreateCampaign}
        title="Create New Campaign"
        message="Give your campaign a descriptive name (e.g., 'Q4 Latex Outreach')."
        placeholder="Campaign Name"
        confirmText="Create Campaign"
      />
    </div>
  );
}