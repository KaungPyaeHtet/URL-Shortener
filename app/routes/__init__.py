def register_routes(app):
    """Register all route blueprints with the Flask app."""
    from app.routes.api import api_bp, short_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(short_bp)
