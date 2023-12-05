// FolderUpload.js
import React, { useState, useRef } from 'react';
import axios from 'axios';
import { Grid, Box, Typography, Button, FormControl, TextField, CircularProgress } from '@mui/material';

const FolderUpload = () => {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    'pilotName': '',
    'weatherConditions': '',
    'comments': ''
  });
  const pilotNameRef = useRef();
  const cloudinessRef = useRef();
  const commentsRef = useRef();

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files);
    // check that the folder being uploaded contains atleast one image
    let imageFlag = false;
    const imgExtensions = ['.jpg', '.jpeg', '.tif'];
    if (files.length > 0) {
      for (let i=0; i< files.length; i++) {
        const fileName = files[i].name;
        const fileNameParts = fileName.split('.');
        const fileExtension = `.${fileNameParts[fileNameParts.length - 1].toLowerCase()}`;
        if (imgExtensions.includes(fileExtension)) {
          imageFlag = true;
          break;
        }
      }
      if (!imageFlag) {
        alert('Please upload a folder with atleast one image in it');
      }
      
      if (imageFlag) {
        setSelectedFiles(files);
      }
    }
    
    
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
  };

  const handleUpload = async () => {
    // Send selectedFiles to the server for processing.
    setLoading(true);
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
      // Send the FormData to the server for processing.
      // will always be localhost since "drone pilot upload" is meant to run locally and process files
      await axios.post('http://127.0.0.1:5000/imgproc', formDataToSend, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      alert('Folder uploaded successfully.');
    } catch (error) {
      alert('Could not upload folder. Please try again');
    } finally {
      // finally reset all states and refernces (clearing the form)
      setLoading(false);
      setFormData({
        'pilotName': '',
        'weatherConditions': '',
        'comments': ''
      });
      setSelectedFiles((prevSelectedFiles) => {
        return [];
      });
      if (pilotNameRef.current) {
        pilotNameRef.current.value = '';
      }
      if (cloudinessRef.current) {
        cloudinessRef.current.value = '';
      }
      if (commentsRef.current) {
        commentsRef.current.value = '';
      }
    }
  };

  return (
    <Box
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100px'
      }}
      margin={5}
    >
      <Grid
        style={{
          backgroundColor: 'rgba(240,247,235,.5)',
          // borderRadius: '10px',
          // border: '1px solid #598445',
          position: 'relative',
          width: '100%',
          // maxWidth: '500px',
          left: '50%',
          transform: 'translateX(-50%)',
        }}
        mt={1}
      >
        <Box mr={1} ml={1} mb={1} mt={1}>
        <FormControl>
          <Grid
            container
            item
            direction="row"
            alignItems="center"
            justifyContent="center"
            spacing={2}
          >
            <Grid item xs={12} sm={12} md={12} lg={12}>
              <Typography variant="h4" gutterBottom align="center">
                Drone pilot - Folder Upload Page
              </Typography>
            </Grid>
            
            <Grid item xs={12} sm={12} md={12} lg={12}>
              <label htmlFor="file-input" style={{border: '2px dashed #ccc', 
              borderRadius: '4px', 
              padding: '2px', 
              textAlign: 'center', 
              cursor: 'pointer',
              display: 'grid',
              minHeight: '100px',
              justifyContent: 'center',
              alignItems: 'center'}}
              fullWidth>
                {selectedFiles.length === 0 ? (
                  <>
                    Drag and drop your folder here or click to select a folder.
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
                hidden
                webkitdirectory="true"
                onChange={handleFileChange}
                disabled={loading}
                // inputRef={filesRef}
              />
            </Grid>
            <Grid item xs={6} sm={6} md={6} lg={6}>
              <TextField required 
              fullWidth type="text" name="pilotName" 
              value={formData.pilotName} onChange={handleInputChange} 
              label="Pilot Name" inputRef={pilotNameRef}
              disabled={loading}/>
            </Grid>
            <Grid item xs={6} sm={6} md={6} lg={6}>
              <TextField required 
              fullWidth type="text" name="cloudiness" 
              value={formData.cloudiness} onChange={handleInputChange} 
              label="Cloudiness" inputRef={cloudinessRef}
              disabled={loading}/>
            </Grid>
            <Grid item xs={12} sm={12} md={12} lg={12}>
              <TextField fullWidth 
              name="comments" value={formData.comments} 
              onChange={handleInputChange} label="Additional comments" 
              inputRef={commentsRef} disabled={loading}/>
            </Grid>
            <Grid item xs={12} sm={12} md={12} lg={12}>
              <Button
                fullWidth
                variant="contained"
                color="primary"
                onClick={handleUpload}
                disabled={(selectedFiles.length === 0) || (pilotNameRef.current.value === '') || (cloudinessRef.current.value === '') || (loading)}
              >
                {loading ? <CircularProgress size={24} color="inherit" /> : 'Upload Folder'}
              </Button>
            </Grid>
          </Grid>
          </FormControl>
        </Box>
      </Grid>
    </Box>
  );
};

export default FolderUpload;
