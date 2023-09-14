import json
from typing import List

import click
from flask import Blueprint, jsonify, request, current_app
from flask_cors import cross_origin

from slapbot import utils
from slapbot.cache import Cache
from slapbot.models import SlapsUser, ActionLog, UserProfile, YoutubeChannel, SpotifyArtist
from sqlalchemy import or_

from slapbot.utils import make_hash, Singleton

routes = Blueprint('routes', __name__)

# Local cache object to handle API caching.
api_cache = Cache()


@routes.route('/api/profile/<int:profile_id>', methods=['GET'])
@cross_origin()
def get_profile_by_id(profile_id: int):
    user_profile = UserProfile.get_by_id(profile_id)

    if user_profile is None:
        return jsonify({'error': 'Profile not found'}), 404

    return jsonify(user_profile.to_dict())


@routes.route('/api/create-profile', methods=['POST'])
@cross_origin()
def create_profile():
    data = request.get_json()

    url = data.get('url')
    if url is None:
        return jsonify({'error': 'No URL provided'}), 400

    user_profile = None
    if 'youtube' in url:
        youtube_channel = YoutubeChannel.query.filter_by(url=url).first()
        if youtube_channel is None:
            youtube_channel = YoutubeChannel.create(url=url)

        user_profile = UserProfile(youtube_channel_id=youtube_channel.id)
    elif 'spotify' in url:
        spotify_artists = SpotifyArtist.query.filter_by(url=url).first()

        if spotify_artists is None:
            spotify_artists = SpotifyArtist(url=url)

        user_profile = UserProfile(spotify_artist_id=spotify_artists.id)
    else:
        return jsonify({'error': 'Only supporting YouTube & Spotify right now'}), 400

    return jsonify(user_profile.to_dict())


@routes.route('/api/profiles', methods=['GET'])
@cross_origin()
def get_profiles():
    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=10, type=int)
    all_items = request.args.get('all', default='false', type=str)
    require_socials = request.args.get('require_socials', default='false', type=str)
    contacted = request.args.get('contacted', default="false", type=str)
    require_message_received = request.args.get('replied', default="false", type=str)

    request_hash = make_hash(request.args.to_dict())

    # Only cache if it's expired
    if not api_cache.has(request_hash) or api_cache.is_expired(request_hash):
        click.echo(f"Page: {page}, Per Page: {per_page}, All Items: {all_items}, Require Socials: {require_socials}")

        query = UserProfile.query.join(SlapsUser, SlapsUser.id == UserProfile.slaps_user_id) \
            .order_by(SlapsUser.follower_count.desc())

        if require_socials == 'true':
            query = query.filter(
                or_(UserProfile.twitter_id != None, UserProfile.instagram_id != None,
                    UserProfile.facebook_user_id != None,
                    UserProfile.youtube_channel_id != None, UserProfile.spotify_id != None))

        if contacted == 'true':
            query = query.filter(or_(SlapsUser.messages.any(), SlapsUser.comments.any()))

        if all_items == 'false':
            query = query.paginate(page=page, per_page=per_page, error_out=False).items
        else:
            query = query.all()

        profile_data = []

        if require_message_received == 'true':
            for profile in query:
                if profile.has_received_reply:
                    profile_data.append(profile.to_dict())
        else:
            profile_data = [profile.to_dict() for profile in query]
        api_cache.set(request_hash, profile_data)
        print(f"Cache miss for {request_hash} & {len(profile_data)} items set to {len(api_cache.get(request_hash))}")
    return jsonify({'profiles': api_cache.get(request_hash)})


@routes.route('/api/actions-log', methods=['GET'])
def get_actions_log_info():
    action_logs = ActionLog.query.all()
    action_logs_data = [log.to_dict() for log in action_logs]

    return jsonify({'action_logs': action_logs_data})
