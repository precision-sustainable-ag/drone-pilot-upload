// FolderUpload.js
import React, { useState } from 'react';
import axios from 'axios';
import { Container, Grid, Box, Typography, Button } from '@mui/material';
import {uploadToServer} from './shared/constants';

const FolderUpload = () => {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [formData, setFormData] = useState({
    'pilotName': '',
    'weatherConditions': ''
  });

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files);
    setSelectedFiles(files);
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
  };

  const handleUpload = async () => {
    // Send selectedFiles to the server for processing.
    const formDataToSend = new FormData();

    // Append each selected file to the FormData object.
    selectedFiles.forEach((file) => {
      formDataToSend.append('files', file);
    });
    const metadataJson = {
      'pilotName': formData.pilotName,
      'cloudiness': formData.cloudiness,
      'comments': formData.comments
    };
    formDataToSend.append('action', 'imageUpload');
    formDataToSend.append('metadata', JSON.stringify(metadataJson));
    try {
      // Send the FormData to your server for processing.
      await axios.post('http://127.0.0.1:5000/imgproc', formDataToSend, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      console.log('Files uploaded successfully.');
    } catch (error) {
      console.error('Error uploading files:', error);
    }
  };

  return (
    <Box display="grid"
    justifyContent="center"
    alignItems="center"
    margin="10vh">
      <Typography variant="h4" gutterBottom>
        Folder Upload Page
      </Typography>
      <div>
      <div style={{paddding:'10px'}}>
        <label htmlFor="file-input" style={{border: '2px dashed #ccc', borderRadius: '4px', padding: '2px', textAlign: 'center', cursor: 'pointer'}}>
          {selectedFiles.length === 0 ? (
            <>
              Drag and drop your file here or click to select a file.
            </>
          ) : (
            <>
              {selectedFiles.length} file(s) selected.
            </>
          )}
        </label>
        <input
          type="file"
          id="file-input"
          multiple
          webkitdirectory="true"
          onChange={handleFileChange}
        />
      </div>
      <div className="col-4" style={{padding: '10px'}}>
        <label>Pilot Name:  </label>
        <input type="text" name="pilotName" value={formData.pilotName} onChange={handleInputChange} />
      </div>
      <div className="col-4" style={{padding: '10px'}}>
        <label>Cloudiness:  </label>
        <input type="text" name="cloudiness" value={formData.cloudiness} onChange={handleInputChange} />
      </div>
      <div className="col-4" style={{padding: '10px'}}>
        <label>Comments:  </label>
        <input type="text" name="comments" value={formData.comments} onChange={handleInputChange} style={{height: '25vh', width: '25vh'}}/>
      </div>
      <Button
        variant="contained"
        color="primary"
        onClick={handleUpload}
        disabled={selectedFiles.length === 0}
      >
        Upload Folder
      </Button>
      </div>
    </Box>
  );
};

export default FolderUpload;
