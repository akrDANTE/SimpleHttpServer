document.body.addEventListener('click', function(event) {
  // Check if the clicked element is an image
  if (event.target.tagName === 'IMG') {
    event.preventDefault(); // Prevents navigating away if the image is inside a link
    
    const img = event.target;
    
    // 1. Coordinates relative to the image as displayed on the screen
    const displayX = event.offsetX;
    const displayY = event.offsetY;
    
    // 2. Coordinates relative to the actual, original unscaled image file
    const originalX = Math.round((displayX / img.clientWidth) * img.naturalWidth);
    const originalY = Math.round((displayY / img.clientHeight) * img.naturalHeight);
    
    // Output the results neatly in a table
    console.log(`%c📍 Click Coordinates for: ${img.src.split('/').pop()}`, 'color: #00d8ff; font-weight: bold;');
    console.table({
      "Displayed Pixels": { X: displayX, Y: displayY },
      "Original File Pixels": { X: originalX, Y: originalY }
    });
  }
});
