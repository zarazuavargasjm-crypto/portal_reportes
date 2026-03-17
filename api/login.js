const { google } = require('googleapis');

function getClient() {
  const credJson = process.env.GOOGLE_CREDENTIALS;
  if (!credJson) {
    console.error('Falta GOOGLE_CREDENTIALS');
    return null;
  }
  let cred;
  try {
    cred = JSON.parse(credJson);
  } catch (e) {
    console.error('GOOGLE_CREDENTIALS no es JSON válido');
    return null;
  }

  const scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly'];
  const auth = new google.auth.JWT(
    cred.client_email,
    null,
    cred.private_key,
    scopes
  );
  return auth;
}

async function leerHoja(auth, spreadsheetId, range) {
  const sheets = google.sheets({ version: 'v4', auth });
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId,
    range
  });
  return res.data.values || [];
}

module.exports = async (req, res) => {
  console.log('=== /api/login llamado ===', req.method);

  const spreadsheetId = process.env.SPREADSHEET_ID;
  if (!spreadsheetId) {
    console.error('Falta SPREADSHEET_ID');
    return res.status(500).json({ error: 'Falta SPREADSHEET_ID' });
  }

  const auth = getClient();
  if (!auth) {
    return res.status(500).json({ error: 'Error con GOOGLE_CREDENTIALS' });
  }

  try {
    const directorio = await leerHoja(auth, spreadsheetId, 'Directorio!A:E');
    const reportes = await leerHoja(auth, spreadsheetId, 'Reportes de entrega!A:M');

    console.log('Filas directorio:', directorio.length);
    console.log('Filas reportes:', reportes.length);

    // Por ahora solo devolvemos datos crudos para verificar
    return res.status(200).json({
      ok: true,
      directorioRows: directorio.length,
      reportesRows: reportes.length
    });
  } catch (e) {
    console.error('Error leyendo Sheets:', e.message);
    return res.status(500).json({ error: 'Error leyendo Google Sheets' });
  }
};
