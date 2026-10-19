/**
 * DentiVoice — Google Sheets receiver
 *
 * Deploy as a Web App that executes as the spreadsheet owner.
 * Store these Script Properties before deployment:
 *   DENTIVOICE_SPREADSHEET_ID = ID of the destination spreadsheet
 *   DENTIVOICE_SHARED_SECRET = same long random secret configured in Render
 */
function doPost(e) {
  try {
    const props = PropertiesService.getScriptProperties();
    const expectedSecret = props.getProperty('DENTIVOICE_SHARED_SECRET');
    const spreadsheetId = props.getProperty('DENTIVOICE_SPREADSHEET_ID');

    if (!expectedSecret || !spreadsheetId) {
      return jsonResponse({ ok: false, error: 'La integración no está configurada.' });
    }

    const payload = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (!payload.secret || payload.secret !== expectedSecret) {
      return jsonResponse({ ok: false, error: 'No autorizado.' });
    }

    const transcript = String(payload.transcript || '').trim();
    if (!transcript) {
      return jsonResponse({ ok: false, error: 'La transcripción está vacía.' });
    }
    if (transcript.length > 50000) {
      return jsonResponse({ ok: false, error: 'La transcripción supera el límite permitido.' });
    }

    const spreadsheet = SpreadsheetApp.openById(spreadsheetId);
    let sheet = spreadsheet.getSheetByName('Dictados');
    if (!sheet) {
      sheet = spreadsheet.insertSheet('Dictados');
      sheet.appendRow(['Fecha y hora', 'Transcripción', 'Estado']);
      sheet.setFrozenRows(1);
      sheet.getRange(1, 1, 1, 3).setFontWeight('bold');
      sheet.getRange('A:A').setNumberFormat('dd/MM/yyyy HH:mm:ss');
      sheet.setColumnWidth(1, 160);
      sheet.setColumnWidth(2, 650);
      sheet.setColumnWidth(3, 130);
      sheet.getRange('B:B').setWrap(true);
    }

    sheet.appendRow([new Date(), transcript, 'Pendiente']);
    return jsonResponse({ ok: true });
  } catch (err) {
    console.error('DentiVoice Sheets integration error: ' + String(err).slice(0, 300));
    return jsonResponse({ ok: false, error: 'No fue posible guardar el dictado.' });
  }
}

function jsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
