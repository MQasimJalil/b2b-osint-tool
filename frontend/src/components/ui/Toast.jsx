import React, { useEffect } from 'react';
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react';

const icons = {
  success: <CheckCircle className="w-5 h-5 text-green-500" />,
  error: <AlertCircle className="w-5 h-5 text-red-500" />,
  info: <Info className="w-5 h-5 text-blue-500" />,
};

const styles = {
  success: 'bg-white border-green-500',
  error: 'bg-white border-red-500',
  info: 'bg-white border-blue-500',
};

export function ToastContainer({ toasts, removeToast }) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`flex items-start p-4 rounded-lg shadow-lg border-l-4 min-w-[300px] max-w-md animate-slide-in ${
            styles[toast.type] || styles.info
          }`}
        >
          <div className="flex-shrink-0 mr-3 mt-0.5">
            {icons[toast.type] || icons.info}
          </div>
          <div className="flex-1 mr-2">
            {toast.title && (
              <h4 className="text-sm font-medium text-gray-900 mb-1">
                {toast.title}
              </h4>
            )}
            <p className="text-sm text-gray-600">{toast.message}</p>
          </div>
          <button
            onClick={() => removeToast(toast.id)}
            className="flex-shrink-0 text-gray-400 hover:text-gray-500 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

export function useToast() {
  const [toasts, setToasts] = React.useState([]);

  const addToast = (type, message, title = '') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, type, message, title }]);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  };

  const removeToast = (id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return {
    toasts,
    addToast,
    removeToast,
    success: (msg, title) => addToast('success', msg, title),
    error: (msg, title) => addToast('error', msg, title),
    info: (msg, title) => addToast('info', msg, title),
  };
}
