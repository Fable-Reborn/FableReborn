import asyncio
import aiohttp
import json
import firebase_admin
from firebase_admin import credentials, storage
import discord
from discord.ext import commands

class BackgroundRemovalTest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def test_bg_removal(self, ctx, mode="upload"):
        """Test the background removal functionality
        
        mode: 'upload' to use your uploaded image, 'example' to use the example URL
        """
        # Set up the API parameters
        pixelcut_api_key = ""
        pixelcut_url = "https://api.developer.pixelcut.ai/v1/remove-background"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-KEY": pixelcut_api_key
        }
        
        # Example mode - use the PixelCut sample URL
        if mode.lower() == "example":
            await ctx.send("Testing with example URL from PixelCut documentation...")
            image_url = "https://cdn3.pixelcut.app/product.jpg"
            await self._process_with_url(ctx, pixelcut_url, headers, image_url)
            return
        
        # Upload mode - handle user's uploaded image
        await ctx.send("Please upload an image to test background removal:")
        
        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and m.attachments
        
        try:
            # Wait for image upload
            msg = await self.bot.wait_for('message', check=check, timeout=60)
            attachment = msg.attachments[0]
            
            if not attachment.height:  # Verify it's an image
                await ctx.send("The attachment doesn't appear to be an image.")
                return
                
            # Try direct URL first (usually works for Discord attachments)
            await ctx.send("First attempting with direct attachment URL...")
            direct_success = await self._process_with_url(ctx, pixelcut_url, headers, attachment.url)
            
            if direct_success:
                await ctx.send("Direct URL method successful!")
                return

            # If direct URL didn't work, try with Firebase
            await ctx.send("Direct URL didn't work. Trying with Firebase upload...")
            
            # Initialize Firebase
            try:
                cred = credentials.Certificate("acc.json")
                if not firebase_admin._apps:
                    firebase_app = firebase_admin.initialize_app(cred)
                else:
                    firebase_app = firebase_admin.get_app()
                
                firebase_storage = storage.bucket("fablerpg-f74c2.appspot.com")
            except Exception as e:
                await ctx.send(f"Failed to initialize Firebase: {e}")
                return
            
            # Download image data
            image_data = await attachment.read()
            
            # Process with Firebase
            try:
                # Upload temporary file to Firebase
                temp_filename = f"temp_test_{ctx.author.id}_{attachment.filename}"
                temp_blob = firebase_storage.blob(temp_filename)
                temp_blob.upload_from_string(image_data)
                
                # Make the blob publicly accessible
                temp_blob.make_public()
                temp_url = temp_blob.public_url
                await ctx.send(f"Temporary image uploaded to: {temp_url}")
                
                # Call PixelCut API with Firebase URL
                await ctx.send("Calling PixelCut API with Firebase URL...")
                firebase_success = await self._process_with_url(ctx, pixelcut_url, headers, temp_url)
                
                # Clean up temporary file regardless of result
                try:
                    temp_blob.delete()
                    await ctx.send("Temporary file cleaned up.")
                except Exception as cleanup_error:
                    await ctx.send(f"Failed to clean up temporary file: {cleanup_error}")
                
                if firebase_success:
                    await ctx.send("Firebase URL method successful!")
                else:
                    await ctx.send("Both direct URL and Firebase methods failed. Please try a different image.")
            except Exception as firebase_error:
                await ctx.send(f"Error with Firebase processing: {firebase_error}")
                
        except asyncio.TimeoutError:
            await ctx.send("Test timed out. Please upload an image within 60 seconds next time.")
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    async def _process_with_url(self, ctx, api_url, headers, image_url):
        """Process an image URL with the PixelCut API"""
        try:
            # Prepare the payload using json.dumps as specified in the example
            payload_data = {
                "image_url": image_url,
                "format": "png"
            }
            payload = json.dumps(payload_data)
            
            await ctx.send(f"Using image URL: {image_url}")
            start_msg = await ctx.send("API call in progress...")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=headers, data=payload) as response:
                    await start_msg.edit(content=f"API responded with status: {response.status}")
                    
                    if response.status == 200:
                        response_data = await response.json()
                        await ctx.send(f"API response: {response_data}")
                        bg_removed_url = response_data.get("result_url")
                        
                        if bg_removed_url:
                            await ctx.send(f"Background removed! Image available at: {bg_removed_url}")
                            return True
                        else:
                            await ctx.send("Background removal API didn't return an image URL.")
                    else:
                        error_text = await response.text()
                        await ctx.send(f"Background removal failed with status {response.status}:\n```\n{error_text[:1500]}\n```")
            
            return False
        except Exception as e:
            await ctx.send(f"Error during API call: {str(e)}")
            return False

async def setup(bot):
    await bot.add_cog(BackgroundRemovalTest(bot))
