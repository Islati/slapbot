import pprint
import traceback

from spotipy import SpotifyClientCredentials

from slapbot.config import Config
from slapbot.utils import Singleton
import spotipy


class SpotifyWrapper(Singleton):
    """
    Wrapper for Spotipy actions to easily serve the internal API.
    """
    _sp: spotipy.Spotify = None
    _client_credentials: SpotifyClientCredentials = None

    def init(self):
        self._client_credentials: SpotifyClientCredentials = SpotifyClientCredentials(client_id=Config.SPOTIFY_CLIENT_ID, client_secret=Config.SPOTIFY_CLIENT_SECRET)
        self._sp: spotipy.Spotify = spotipy.Spotify(client_credentials_manager=self._client_credentials)

    def search_for_artist(self, artist_id_or_name) -> dict | None:
        """
        Get artist info for a given artist ID.
        :param artist_id_or_name: Spotify artist ID (artist:<name>/<id>)
        """
        result = self._sp.search(q=f"{artist_id_or_name}", type="artist")
        return result

    def get_discography(self, artist_or_artist_id: dict | str) -> dict | None:
        """
        Get artist info for a given artist ID.
        :param artist_id_or_name: Spotify artist ID (artist:<name>/<id>)
        """
        if isinstance(artist_or_artist_id, str):
            artist = self.get_artist(artist_or_artist_id)
        else:
            artist = artist_or_artist_id

        albums = self.get_artist_albums(artist)

        for album in albums:
            album['tracks'] = self.get_album_tracks(album)
        artist['albums'] = albums

        singles = self.get_artist_singles(artist)
        if len(singles) > 0:
            artist['singles'] = singles

        return artist

    def get_artists_collaborated_with(self, artist: dict) -> dict[str, dict]:
        """
        Get all artists collaborated with for a given artist ID.
        :param artist: Spotify artist ID (artist:<name>/<id>)
        """
        artists = {}
        discography = self.get_discography(artist)  # large dict return value
        appearances = self.get_artist_appearances(artist['id'])

        for album in discography['albums']:
            for track in album['tracks']:
                for artist in track['artists']:
                    if artist['id'] not in artists.keys():
                        artists[artist['id']] = artist
                #
                # for artist in self.get_artists_featured_on_track(track):
                #     if artist['id'] not in artists.keys():
                #         artists[artist['id']] = artist

        for single in discography['singles']:
            for artist in single['artists']:
                if artist['id'] not in artists.keys():
                    artists[artist['id']] = artist

            # for artist in self.get_artists_featured_on_track(single):
            #     if artist['id'] not in artists.keys():
            #         artists[artist['id']] = artist

        for appearance in appearances:
            for artist in appearance['artists']:
                if artist['id'] not in artists.keys():
                    artists[artist['id']] = artist

        return artists

    def get_artists_featured_on_album(self, album) -> list[dict]:
        """
        Get all artists featured on an album.
        :param album: Spotify album ID (album:<name>/<id>)
        """
        artists = []
        tracks = self.get_album_tracks(album)
        for track in tracks:
            for artist in track['artists']:
                if artist['id'] not in artists:
                    artists.append(artist)
        return artists

    def get_artists_featured_on_track(self, track: dict | str) -> list[dict]:
        """
        Get all artists featured on a track.
        :param track: Spotify track ID (track:<name>/<id>)
        """
        artists = []
        try:
            track = self.get_track(track) if isinstance(track, dict) else track
        except:
            traceback.print_exc()
            pprint.pprint("===== TRACK ====")
            pprint.pprint(track)
            return []


        for artist in track['artists']:
            if artist['id'] not in artists:
                artists.append(artist)
        return artists

    def get_artist(self, artist_id_or_name) -> dict | None:
        """
        Get artist info for a given artist ID.
        :param artist_id_or_name: Spotify artist ID (spotify:artist:<name>/<id>)
        """
        result = self._sp.artist(artist_id_or_name)
        return result

    def get_track(self, track_id_or_name: dict | str) -> dict | None:
        """
        Get track info for a given track ID.
        :param track_id_or_name: Spotify track ID (spotify:track:<name>/<id>)
        """
        result = self._sp.track(track_id_or_name['id'] if isinstance(track_id_or_name, dict) else track_id_or_name)
        return result

    def get_artist_albums(self, artist):
        """
        Get all albums for a given artist ID.
        :param artist: Spotify artist ID (artist:<name>/<id>)
        """
        albums = []
        results = self._sp.artist_albums(artist['id'], album_type='album')
        albums.extend(results['items'])
        while results['next']:
            results = self._sp.next(results)
            albums.extend(results['items'])

        return albums

    def get_artist_singles(self, artist):
        """
        Get all singles for a given artist ID.
        :param artist: Spotify artist ID (artist:<name>/<id>)
        """
        singles = []
        results = self._sp.artist_albums(artist['id'], album_type='single')
        singles.extend(results['items'])
        while results['next']:
            results = self._sp.next(results)
            singles.extend(results['items'])

        return singles

    def get_artist_appearances(self, artist: str | dict):
        """
        Get all appearances for a given artist ID.
        :param artist: Spotify artist ID (artist:<name>/<id>)
        """
        appearances = []
        results = self._sp.artist_albums(artist['id'] if isinstance(artist,dict) else artist, album_type='appears_on')
        appearances.extend(results['items'])
        while results['next']:
            results = self._sp.next(results)
            appearances.extend(results['items'])

        return appearances

    def get_album_tracks(self, album):
        """
        Get all tracks for a given album ID.
        :param album: Spotify album ID (album:<name>/<id>)
        """
        tracks = []
        results = self._sp.album_tracks(album['id'])
        tracks.extend(results['items'])
        while results['next']:
            results = self._sp.next(results)
            tracks.extend(results['items'])
        return tracks

    def get_related_artists(self, artist_id) -> list[dict]:
        """
        Get related artists for a given artist ID.
        :param artist_id: Spotify artist ID (artist:<name>/<id>)
        """
        result = self._sp.search(q=f"{artist_id}", type="artist")

        related_artists = []

        try:
            # name = result['artists']['items'][0]['name']
            uri = result['artists']['items'][0]['uri']

            related = self._sp.artist_related_artists(uri)
            for artist in related['artists']:
                related_artists.append(artist)
        except:
            pass

        return related_artists
