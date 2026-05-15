// Wildlife Camera -- Google Apps Script Upload Handler
// Deploy settings: Execute as: Me | Who has access: Anyone
// After deploying, copy the Web App URL to config/.env as GOOGLE_SCRIPT_URL

function doPost(e) {
  try {
    var mimeType = (e.postData && e.postData.type) ? e.postData.type : "video/mp4";
    var filename = "clip_" + new Date().getTime() + ".mp4";
    var blob = Utilities.newBlob(e.postData.contents, mimeType, filename);

    var folderName = "WildlifeCam";
    var folders = DriveApp.getFoldersByName(folderName);
    var folder = folders.hasNext() ? folders.next() : DriveApp.createFolder(folderName);

    var file = folder.createFile(blob);

    return ContentService
      .createTextOutput(JSON.stringify({ status: "ok", fileId: file.getId() }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}