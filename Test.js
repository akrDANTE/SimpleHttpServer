document.body.addEventListener('click', function(event) {
  // Check if the clicked element is an image
  if (event.target.tagName === 'IMG') {
    event.preventDefault(); 
    
    const img = event.target;
    
    // Coordinates relative to the image as displayed on the screen
    const displayX = event.offsetX;
    const displayY = event.offsetY;
    
    // Scale coordinates to a theoretical 1920x1080 canvas
    const targetWidth = 1920;
    const targetHeight = 1080;
    
    // Calculate the scaled coordinates
    // We divide the clicked X by the displayed width to get a percentage (0.0 to 1.0)
    // Then multiply by our target width (1920)
    const scaledX = Math.round((displayX / img.clientWidth) * targetWidth);
    const scaledY = Math.round((displayY / img.clientHeight) * targetHeight);
    
    console.log(`%c📍 Scaled Coordinates for: ${img.src.split('/').pop()}`, 'color: #00d8ff; font-weight: bold;');
    console.table({
      "Displayed Pixels": { X: displayX, Y: displayY },
      "Scaled (1920x1080)": { X: scaledX, Y: scaledY }
    });
  }
});
