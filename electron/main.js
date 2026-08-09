const { app, BrowserWindow } = require('electron');
const path = require('path');

// Packaged builds (npm run build) already pick up productName "VoiceVault"
// and the real .icns for the Dock/Cmd+Tab/menu bar via package.json's
// build config. This block only covers the unpackaged `npm start` dev
// path, where Electron otherwise shows up as generic "Electron".
app.setName('VoiceVault');
if (!app.isPackaged && process.platform === 'darwin' && app.dock) {
  app.dock.setIcon(path.join(__dirname, 'build', 'icon.png'));
}

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1150,
    height: 780,
    minWidth: 760,
    minHeight: 480,
    title: 'VoiceVault',
    backgroundColor: '#0d1117',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

// Without this, launching the dashboard (e.g. repeatedly from the menu
// bar's "Open Dashboard"/"Meeting" items) spawns a new process and window
// each time instead of focusing the existing one — the same duplicate-
// instance class of bug the Python menu bar app had before it got a
// PID-file guard.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(createWindow);

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
}
