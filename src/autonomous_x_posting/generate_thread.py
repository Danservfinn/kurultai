from typing import List, Dict

def generate_thread_from_analysis(analysis: Dict, article: Dict) -> List[str]:
    """
    Generates a Twitter thread from Parse Platform analysis.
    Ensures that each tweet adheres to the 280-character limit.
    """
    if not analysis:
        return []

    title = article.get('title', 'Recent News')
    link = article.get('link', '')
    
    thread = []
    
    # Tweet 1: Hook and Article Link
    tweet1 = f"📰 {title}\n\nWe ran this through the Parse Platform AI for deeper analysis. Here's what we found:\n\n{link}"
    thread.append(tweet1[:280])
    
    # Tweet 2: Parse Summary
    summary = analysis.get('summary', 'No summary available.')
    tweet2 = f"🧠 Parse Analysis Summary:\n\n{summary}"
    if len(tweet2) > 280:
        tweet2 = tweet2[:277] + "..."
    thread.append(tweet2)
    
    # Tweet 3: Key Points
    key_points = analysis.get('key_points', [])
    if key_points:
        points_str = "\n".join([f"• {kp}" for kp in key_points[:3]])
        tweet3 = f"🔑 Key Takeaways:\n\n{points_str}"
        if len(tweet3) > 280:
            tweet3 = tweet3[:277] + "..."
        thread.append(tweet3)
        
    # Tweet 4: Call to Action
    tweet4 = "Want to uncover hidden biases and get deeper insights from the media you consume? Try Agent Parse today! #AI #MediaAnalysis #KublaiAI"
    thread.append(tweet4[:280])
    
    return thread

def generate_capabilities_thread() -> List[str]:
    """Generates a promotional thread about Agent Parse capabilities."""
    return [
        "🤖 Meet Agent Parse: Your personal AI media analyst.\n\nIn an era of information overload, understanding the true narrative is harder than ever. We built Parse to change that. 🧵 1/4",
        "Agent Parse doesn't just summarize articles. It analyzes:\n- Underlying bias and framing\n- Rhetorical devices used\n- Logical fallacies\n- Emotional manipulation tactics 2/4",
        "By breaking down how news is constructed, Parse empowers you to consume information critically and objectively. It's not about what to think, but HOW to think about what you read. 3/4",
        "Experience the future of media consumption. Integrate Parse Platform into your workflow today and see beyond the headlines. 🚀 #AgentParse #AI #KublaiAI 4/4"
    ]
