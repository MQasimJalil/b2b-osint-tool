import React, { useState, useRef } from 'react';
import { Loader2, Wand2, Send, Save, RotateCcw, X, Edit3, ChevronDown, Paperclip, Trash2, File as FileIcon } from 'lucide-react';
import ReactQuill from 'react-quill';
import 'react-quill/dist/quill.snow.css';

export function EmailComposer({ draft, onSave, onSend, onClose }) {
  const [subject, setSubject] = useState(draft?.subject || '');
  const [body, setBody] = useState(draft?.body || '');
  const [generating, setGenerating] = useState(false);
  const [showSubjectOptions, setShowSubjectOptions] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const fileInputRef = useRef(null);

  const subjectOptions = draft?.subject_line_options || [
    "Partnership Opportunity: Raqim x YourCompany",
    "Quick question regarding your glove manufacturing",
    "Helping you scale your production"
  ];

  const handleRegenerate = async () => {
    // Placeholder for regeneration
    setGenerating(true);
    setTimeout(() => setGenerating(false), 2000);
  };

  const handleFileSelect = (e) => {
    if (e.target.files) {
      setAttachments([...attachments, ...Array.from(e.target.files)]);
    }
  };

  const removeAttachment = (index) => {
    setAttachments(attachments.filter((_, i) => i !== index));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
      <div className="bg-white w-full max-w-4xl h-[90vh] rounded-lg shadow-xl flex flex-col overflow-hidden animate-fade-in">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div>
            <h2 className="text-xl font-bold text-gray-900 flex items-center">
              <Edit3 className="w-5 h-5 mr-2 text-blue-600" />
              Edit Email Draft
            </h2>
            <p className="text-sm text-gray-500">To: {draft?.to_emails?.[0] || 'recipient@example.com'}</p>
          </div>
          <div className="flex gap-2">
            <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
              <X className="w-5 h-5 text-gray-500" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          
          {/* Subject Line */}
          <div className="relative">
            <label className="block text-sm font-medium text-gray-700 mb-1">Subject Line</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Enter subject line..."
              />
              <button
                onClick={() => setShowSubjectOptions(!showSubjectOptions)}
                className="px-3 py-2 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 text-gray-600"
              >
                <ChevronDown className="w-5 h-5" />
              </button>
            </div>
            
            {showSubjectOptions && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-10 p-2">
                <p className="text-xs font-semibold text-gray-500 mb-2 px-2 uppercase">AI Suggestions</p>
                {subjectOptions.map((opt, i) => (
                  <button
                    key={i}
                    onClick={() => { setSubject(opt); setShowSubjectOptions(false); }}
                    className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-blue-50 rounded-md transition-colors"
                  >
                    {opt}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Editor */}
          <div className="h-96 flex flex-col">
            <label className="block text-sm font-medium text-gray-700 mb-1">Email Body</label>
            <ReactQuill 
              theme="snow" 
              value={body} 
              onChange={setBody} 
              className="flex-1 bg-white overflow-hidden"
              modules={{
                toolbar: [
                  [{ 'header': [1, 2, false] }],
                  ['bold', 'italic', 'underline', 'strike', 'blockquote'],
                  [{'list': 'ordered'}, {'list': 'bullet'}],
                  ['link', 'clean']
                ],
              }}
            />
          </div>

          {/* Tools & Attachments */}
          <div className="space-y-4">
            
            {/* Toolbar */}
            <div className="flex items-center justify-between bg-gray-50 p-3 rounded-lg border border-gray-200">
              <div className="flex items-center gap-2">
                 {/* AI Tools */}
                 <button 
                  onClick={handleRegenerate}
                  disabled={generating}
                  className="px-3 py-1.5 bg-white border border-purple-200 text-purple-700 text-sm rounded hover:bg-purple-50 transition-colors flex items-center"
                >
                  {generating ? <Loader2 className="w-3 h-3 mr-2 animate-spin"/> : <Wand2 className="w-3 h-3 mr-2" />}
                  Regenerate
                </button>
              </div>

              <div>
                <input 
                  type="file" 
                  multiple 
                  ref={fileInputRef} 
                  className="hidden" 
                  onChange={handleFileSelect}
                />
                <button 
                  onClick={() => fileInputRef.current?.click()}
                  className="px-3 py-1.5 bg-white border border-gray-300 text-gray-700 text-sm rounded hover:bg-gray-50 transition-colors flex items-center"
                >
                  <Paperclip className="w-3 h-3 mr-2" />
                  Attach Files
                </button>
              </div>
            </div>

            {/* Attachment List */}
            {attachments.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {attachments.map((file, i) => (
                  <div key={i} className="flex items-center justify-between p-2 bg-blue-50 border border-blue-100 rounded text-sm text-blue-900">
                    <div className="flex items-center truncate">
                      <FileIcon className="w-4 h-4 mr-2 text-blue-500 flex-shrink-0" />
                      <span className="truncate">{file.name}</span>
                    </div>
                    <button onClick={() => removeAttachment(i)} className="text-blue-400 hover:text-red-500 ml-2">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex justify-between items-center">
          <button 
            onClick={() => { setSubject(draft.subject); setBody(draft.body); }}
            className="flex items-center text-gray-600 hover:text-gray-900"
          >
            <RotateCcw className="w-4 h-4 mr-2" /> Reset
          </button>
          <div className="flex gap-3">
            <button 
              onClick={() => onSave({ ...draft, subject, body })}
              className="flex items-center px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium"
            >
              <Save className="w-4 h-4 mr-2" /> Save Draft
            </button>
            <button 
              onClick={() => onSend({ ...draft, subject, body, attachments })}
              className="flex items-center px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium shadow-sm"
            >
              <Send className="w-4 h-4 mr-2" /> Send Now
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
