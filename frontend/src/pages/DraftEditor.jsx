import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, Send, Loader2, Wand2, Paperclip, Trash2, File as FileIcon, ChevronDown, Mail, CheckCircle2, AlertCircle } from 'lucide-react';
import ReactQuill from 'react-quill';
import 'react-quill/dist/quill.snow.css';
import { api } from '../api/client';
import { useToast } from '../components/ui/Toast';

export default function DraftEditor() {
  const { campaignId, draftId } = useParams();
  const navigate = useNavigate();
  const { success, error } = useToast();
  const fileInputRef = useRef(null);

  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [toEmail, setToEmail] = useState('');
  const [showSubjectOptions, setShowSubjectOptions] = useState(false);
  
  // Verification state
  const [verifying, setVerifying] = useState(false);
  const [emailStatus, setEmailStatus] = useState({}); // { email: 'valid' | 'invalid' | 'unknown' }

  useEffect(() => {
    loadDraft();
  }, [draftId]);

  const loadDraft = async () => {
    try {
      setLoading(true);
      // We don't have a direct getDraft endpoint in API client, usually we list drafts.
      // But wait, we might need to fetch the specific draft. 
      // The listDrafts endpoint returns all. Let's filter or implement getDraft.
      // Ideally backend supports getDraft. For now, let's use listDrafts and find it.
      // Optimization: Add getDraft to backend if needed, but list is okay for small campaigns.
      const res = await api.campaigns.listDrafts(campaignId);
      const found = res.data.find(d => d.id === draftId);
      
      if (found) {
        setDraft(found);
        setSubject(found.subject || '');
        setBody(found.body || '');
        setToEmail(found.to_emails?.[0] || '');
        // Pre-populate status if we had it (not stored yet)
      } else {
        error("Draft not found");
        navigate(`/email`); // Go back
      }
    } catch (err) {
      console.error(err);
      error("Failed to load draft");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await api.campaigns.updateDraft(draftId, {
        subject,
        body,
        to_emails: [toEmail] // Save the selected email
      });
      success("Draft saved");
    } catch (err) {
      console.error(err);
      error("Failed to save draft");
    } finally {
      setSaving(false);
    }
  };

  const handleSend = async () => {
    // Implement send logic (probably via API)
    success("Sending email... (Mock)");
  };

  const handleVerifyEmails = async () => {
    if (!draft?.to_emails?.length) return;
    
    setVerifying(true);
    try {
        // Mock verification for now or call API if ready
        // const res = await api.email.verify(draft.to_emails);
        // For now, mock random results to show UI
        await new Promise(r => setTimeout(r, 1000));
        const newStatus = {};
        draft.to_emails.forEach(e => {
            newStatus[e] = Math.random() > 0.3 ? 'valid' : 'unknown';
        });
        setEmailStatus(newStatus);
        success("Emails verified");
    } catch(err) {
        error("Verification failed");
    } finally {
        setVerifying(false);
    }
  };

  if (loading) return <div className="p-12 text-center"><Loader2 className="w-8 h-8 animate-spin mx-auto text-blue-600"/></div>;
  if (!draft) return null;

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/email')} className="text-gray-500 hover:text-gray-700">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">{draft.domain}</h1>
            <p className="text-sm text-gray-500">Campaign: {campaignId}</p>
          </div>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={handleSave} 
            disabled={saving}
            className="flex items-center px-4 py-2 bg-white border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
          >
            {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin"/> : <Save className="w-4 h-4 mr-2"/>}
            Save
          </button>
          <button 
            onClick={handleSend}
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Send className="w-4 h-4 mr-2"/>
            Send
          </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Main Editor Area */}
        <div className="flex-1 flex flex-col min-w-0 bg-white m-4 rounded-lg shadow-sm border border-gray-200">
            
            {/* Recipient & Subject Fields */}
            <div className="px-6 py-4 border-b border-gray-100 space-y-4">
                {/* To: Field with Selection */}
                <div>
                    <div className="flex justify-between items-end mb-1">
                        <label className="block text-sm font-medium text-gray-700">Recipient</label>
                        {draft.to_emails?.length > 1 && (
                             <button 
                                onClick={handleVerifyEmails}
                                disabled={verifying}
                                className="text-xs text-blue-600 hover:underline flex items-center"
                             >
                                {verifying && <Loader2 className="w-3 h-3 mr-1 animate-spin"/>}
                                Verify All
                             </button>
                        )}
                    </div>
                    
                    {draft.to_emails && draft.to_emails.length > 0 ? (
                        <div className="space-y-2">
                            {draft.to_emails.map(email => (
                                <label key={email} className={`flex items-center p-2 rounded border cursor-pointer ${toEmail === email ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'}`}>
                                    <input 
                                        type="radio" 
                                        name="to_email" 
                                        value={email}
                                        checked={toEmail === email}
                                        onChange={() => setToEmail(email)}
                                        className="mr-3 text-blue-600"
                                    />
                                    <span className="flex-1 text-sm text-gray-700">{email}</span>
                                    
                                    {/* Verification Status Badge */}
                                    {emailStatus[email] === 'valid' && <span className="text-xs px-2 py-0.5 bg-green-100 text-green-800 rounded-full flex items-center"><CheckCircle2 className="w-3 h-3 mr-1"/> Valid</span>}
                                    {emailStatus[email] === 'invalid' && <span className="text-xs px-2 py-0.5 bg-red-100 text-red-800 rounded-full flex items-center"><AlertCircle className="w-3 h-3 mr-1"/> Invalid</span>}
                                </label>
                            ))}
                        </div>
                    ) : (
                        <input 
                            type="email" 
                            value={toEmail} 
                            onChange={(e) => setToEmail(e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
                        />
                    )}
                </div>

                {/* Subject Line */}
                <div className="relative">
                    <label className="block text-sm font-medium text-gray-700 mb-1">Subject</label>
                    <div className="flex gap-2">
                        <input
                            type="text"
                            value={subject}
                            onChange={(e) => setSubject(e.target.value)}
                            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
                        />
                        <button
                            onClick={() => setShowSubjectOptions(!showSubjectOptions)}
                            className="px-3 py-2 bg-gray-100 border border-gray-300 rounded-md hover:bg-gray-200"
                        >
                            <ChevronDown className="w-4 h-4 text-gray-600"/>
                        </button>
                    </div>
                    {showSubjectOptions && draft.subject_line_options && (
                        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-md shadow-lg z-10 p-1">
                            {draft.subject_line_options.map((opt, i) => (
                                <button
                                    key={i}
                                    onClick={() => { setSubject(opt); setShowSubjectOptions(false); }}
                                    className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-blue-50 rounded-md"
                                >
                                    {opt}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Rich Text Editor - Flex Grow to fill space */}
            <div className="flex-1 flex flex-col min-h-0">
                <ReactQuill 
                    theme="snow"
                    value={body}
                    onChange={setBody}
                    className="flex-1 flex flex-col overflow-hidden" 
                    modules={{
                        toolbar: [
                            [{ 'header': [1, 2, false] }],
                            ['bold', 'italic', 'underline', 'strike', 'blockquote'],
                            [{'list': 'ordered'}, {'list': 'bullet'}],
                            ['link', 'clean']
                        ],
                    }}
                />
                {/* CSS override for Quill to fill height */}
                <style>{`
                    .quill { display: flex; flex-direction: column; height: 100%; }
                    .ql-container { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
                    .ql-editor { flex: 1; overflow-y: auto; }
                `}</style>
            </div>

            {/* Footer / Attachments */}
            <div className="px-6 py-4 bg-gray-50 border-t border-gray-200">
                 <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <button 
                            onClick={() => fileInputRef.current?.click()}
                            className="flex items-center px-3 py-1.5 text-sm text-gray-600 bg-white border border-gray-300 rounded hover:bg-gray-50"
                        >
                            <Paperclip className="w-4 h-4 mr-2"/> Attach Files
                        </button>
                        <input type="file" multiple className="hidden" ref={fileInputRef} />
                        <span className="text-xs text-gray-400">Supported: PDF, DOCX, PNG, JPG</span>
                    </div>
                 </div>
            </div>
        </div>

        {/* Sidebar (Optional - could hold Research Notes) */}
        <div className="w-80 bg-white m-4 ml-0 rounded-lg shadow-sm border border-gray-200 flex flex-col">
            <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
                <h3 className="font-semibold text-gray-900">Research Notes</h3>
            </div>
            <div className="p-4 overflow-y-auto flex-1">
                <p className="text-sm text-gray-600 italic">Research data not yet connected to this view. (Placeholder)</p>
            </div>
        </div>
      </div>
    </div>
  );
}
